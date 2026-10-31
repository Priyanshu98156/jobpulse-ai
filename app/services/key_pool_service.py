import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from app.models import AIKey
from app.config import settings

logger = logging.getLogger(__name__)

# Provider default presets
PROVIDER_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile"
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free"
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest"
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "default_model": "llama3.1-8b"
    },
    "gemini": {
        "base_url": "",
        "default_model": "gemini-2.5-flash"
    },
    "custom": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3"
    }
}

class KeyPoolService:
    def __init__(self):
        self._round_robin_idx = 0
        self._gemini_clients = {} # cache by api_key

    def get_healthy_keys(self, db: Session) -> List[AIKey]:
        """
        Retrieves all enabled keys. Automatically clears cooldowns
        for keys whose cooldown_until timestamp has expired.
        """
        all_enabled = db.query(AIKey).filter(AIKey.enabled == True).all()
        healthy = []
        now = datetime.utcnow()
        changed = False

        for k in all_enabled:
            if k.is_in_cooldown:
                if k.cooldown_until and k.cooldown_until <= now:
                    k.is_in_cooldown = False
                    k.cooldown_until = None
                    changed = True
                    healthy.append(k)
            else:
                healthy.append(k)

        if changed:
            db.commit()

        # If database has no keys yet, but environment variables have a key, create a default entry
        if not all_enabled and (settings.AI_API_KEY or settings.GEMINI_API_KEY):
            env_key = (settings.AI_API_KEY or settings.GEMINI_API_KEY).strip()
            prov = (settings.AI_PROVIDER or "gemini").lower().strip()
            preset = PROVIDER_PRESETS.get(prov, {})
            model = settings.AI_MODEL.strip() if settings.AI_MODEL else preset.get("default_model", "llama-3.3-70b-versatile")
            base_url = settings.AI_BASE_URL.strip() if settings.AI_BASE_URL else preset.get("base_url", "")
            
            new_key = AIKey(
                label=f"Default {prov.title()} Key (from .env)",
                provider=prov,
                api_key=env_key,
                model=model,
                base_url=base_url,
                enabled=True
            )
            db.add(new_key)
            db.commit()
            db.refresh(new_key)
            healthy.append(new_key)

        return healthy

    def _execute_single_key(self, key: AIKey, prompt: str) -> str:
        """
        Sends the prompt to the specific key. Raises an exception if HTTP 429 or quota limit is encountered.
        """
        provider = key.provider.lower().strip()
        model = key.model or PROVIDER_PRESETS.get(provider, {}).get("default_model", "gemini-2.5-flash")

        # 1. Google Gemini
        if provider == "gemini":
            from google import genai
            if key.api_key not in self._gemini_clients:
                self._gemini_clients[key.api_key] = genai.Client(api_key=key.api_key)
            client = self._gemini_clients[key.api_key]

            resp = client.models.generate_content(
                model=model or "gemini-2.5-flash",
                contents=prompt
            )
            return resp.text.strip()

        # 2. OpenAI-compatible providers: Groq, OpenRouter, Mistral, Cerebras, Custom
        base_url = key.base_url or PROVIDER_PRESETS.get(provider, {}).get("base_url", "")
        if not base_url:
            raise ValueError(f"No API Base URL configured for provider {provider}")

        target_url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {key.api_key}",
            "Content-Type": "application/json"
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "JobPulse AI Key Pool"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }

        with httpx.Client(timeout=35.0) as http_client:
            res = http_client.post(target_url, headers=headers, json=payload)
            
            # Check rate limit status codes
            if res.status_code == 429:
                retry_header = res.headers.get("retry-after")
                cooldown_sec = int(retry_header) if retry_header and retry_header.isdigit() else 900 # default 15 min
                raise RateLimitException(f"HTTP 429 Too Many Requests from {provider}", cooldown_seconds=cooldown_sec)

            if res.status_code == 403 and ("quota" in res.text.lower() or "limit" in res.text.lower()):
                raise RateLimitException(f"HTTP 403 Quota Exceeded from {provider}", cooldown_seconds=1800)

            if res.status_code != 200:
                raise Exception(f"{provider.upper()} API returned status {res.status_code}: {res.text[:300]}")

            data = res.json()
            choices = data.get("choices", [])
            if not choices:
                raise Exception(f"Empty choices returned by {provider}")

            content = choices[0].get("message", {}).get("content", "").strip()
            return content

    def call_with_failover(self, prompt: str, db: Session) -> Tuple[Optional[str], Optional[str]]:
        """
        Executes prompt across healthy keys using round-robin distribution.
        If a key hits rate limit or quota, automatically places it in cooldown,
        switches to the next healthy key in the pool, and retries.
        Returns: (generated_text, key_label_used)
        """
        tried_key_ids = set()

        while True:
            healthy_keys = self.get_healthy_keys(db)
            available = [k for k in healthy_keys if k.id not in tried_key_ids]

            if not available:
                logger.warning("All available keys in the pool have been exhausted or are in cooldown.")
                return None, None

            # Round-robin selection
            selected_key = available[self._round_robin_idx % len(available)]
            self._round_robin_idx += 1
            tried_key_ids.add(selected_key.id)

            selected_key.total_requests += 1
            selected_key.last_used_at = datetime.utcnow()

            try:
                logger.info(f"Routing AI request to key #{selected_key.id} [{selected_key.label}] ({selected_key.provider}:{selected_key.model})")
                text = self._execute_single_key(selected_key, prompt)
                selected_key.successful_requests += 1
                selected_key.last_error_message = ""
                db.commit()
                return text, f"{selected_key.label} ({selected_key.provider})"

            except RateLimitException as rle:
                logger.warning(f"Rate limit hit on key #{selected_key.id} [{selected_key.label}]: {rle}. Moving to cooldown for {rle.cooldown_seconds}s and failing over...")
                selected_key.is_in_cooldown = True
                selected_key.cooldown_until = datetime.utcnow() + timedelta(seconds=rle.cooldown_seconds)
                selected_key.rate_limit_hits += 1
                selected_key.last_error_message = str(rle)
                db.commit()
                continue # Try next key

            except Exception as e:
                err_msg = str(e)
                # Detect rate limit messages inside SDK exceptions (e.g. Gemini 429)
                if "429" in err_msg or "resource_exhausted" in err_msg.lower() or "quota" in err_msg.lower():
                    logger.warning(f"Quota error on key #{selected_key.id} [{selected_key.label}]: {err_msg}. Moving to cooldown and failing over...")
                    selected_key.is_in_cooldown = True
                    selected_key.cooldown_until = datetime.utcnow() + timedelta(minutes=15)
                    selected_key.rate_limit_hits += 1
                    selected_key.last_error_message = err_msg
                    db.commit()
                    continue

                logger.error(f"Error on key #{selected_key.id} [{selected_key.label}]: {err_msg}. Failing over to next key...")
                selected_key.last_error_message = err_msg
                db.commit()
                continue

    def test_key(self, key: AIKey) -> Dict[str, Any]:
        """
        Sends a quick 1-token prompt to verify if the key is valid and reachable.
        """
        t0 = time.time()
        try:
            test_prompt = "Say 'OK' in one word."
            res = self._execute_single_key(key, test_prompt)
            latency = int((time.time() - t0) * 1000)
            return {
                "success": True,
                "latency_ms": latency,
                "message": f"Success! Responded in {latency}ms: '{res[:50]}'"
            }
        except Exception as e:
            return {
                "success": False,
                "latency_ms": int((time.time() - t0) * 1000),
                "message": f"Test failed: {str(e)}"
            }

class RateLimitException(Exception):
    def __init__(self, message: str, cooldown_seconds: int = 900):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds

key_pool_service = KeyPoolService()
