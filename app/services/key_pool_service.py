import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from app.models import AIKey
from app.config import settings

logger = logging.getLogger(__name__)

class RateLimitException(Exception):
    def __init__(self, message: str, cooldown_seconds: int = 900):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds

# Strict allowlist of vetted free/economical models per provider
PROVIDER_ALLOWLISTS = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen-2.5-32b",
        "mistral-saba-24b"
    ],
    "openrouter": [
        "nvidia/nemotron-3.5-lightning:free",
        "liquid/lfm-2.5-2.6b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free"
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash"
    ],
    "sambanova": [
        "Meta-Llama-3.3-70B-Instruct",
        "DeepSeek-V3.1",
        "MiniMax-M3.1-Flash"
    ],
    "nvidia": [
        "minimaxai/minimax-m3.1-flash",
        "meta/llama-3.3-70b-instruct"
    ],
    "mistral": [
        "mistral-small-latest",
        "open-mistral-nemo"
    ],
    "cerebras": [
        "llama3.1-8b",
        "llama-3.3-70b"
    ],
    "cohere": [
        "command-a-03-2025",
        "c4ai-aya-expanse-32b"
    ],
    "custom": [
        "llama3",
        "llama3.2"
    ]
}

# Provider default presets with fallback chains
PROVIDER_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "fallbacks": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen-2.5-32b"]
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "nvidia/nemotron-3.5-lightning:free",
        "fallbacks": ["nvidia/nemotron-3.5-lightning:free", "liquid/lfm-2.5-2.6b:free", "meta-llama/llama-3.3-70b-instruct:free"]
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "default_model": "Meta-Llama-3.3-70B-Instruct",
        "fallbacks": ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1", "MiniMax-M3.1-Flash"]
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "minimaxai/minimax-m3.1-flash",
        "fallbacks": ["minimaxai/minimax-m3.1-flash", "meta/llama-3.3-70b-instruct"]
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "fallbacks": ["mistral-small-latest", "open-mistral-nemo"]
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "default_model": "llama3.1-8b",
        "fallbacks": ["llama3.1-8b", "llama-3.3-70b"]
    },
    "cohere": {
        "base_url": "https://api.cohere.com/v2",
        "default_model": "command-a-03-2025",
        "fallbacks": ["command-a-03-2025", "c4ai-aya-expanse-32b"]
    },
    "gemini": {
        "base_url": "",
        "default_model": "gemini-2.5-flash",
        "fallbacks": ["gemini-2.5-flash", "gemini-1.5-flash"]
    },
    "custom": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "fallbacks": ["llama3", "llama3.2"]
    }
}

class KeyPoolService:
    def __init__(self):
        self._round_robin_idx = 0
        self._gemini_clients = {}

    def get_healthy_keys(self, db: Session) -> List[AIKey]:
        all_enabled = db.query(AIKey).filter(AIKey.enabled == True).all()
        healthy = []
        now = datetime.now(timezone.utc)
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

        if not all_enabled and (settings.AI_API_KEY or settings.GEMINI_API_KEY):
            env_key = (settings.AI_API_KEY or settings.GEMINI_API_KEY).strip()
            prov = (settings.AI_PROVIDER or "gemini").lower().strip()
            preset = PROVIDER_PRESETS.get(prov, {})
            model = settings.AI_MODEL.strip() if settings.AI_MODEL else preset.get("default_model", "gemini-2.5-flash")
            base_url = settings.AI_BASE_URL.strip() if settings.AI_BASE_URL else preset.get("base_url", "")
            
            new_key = AIKey(
                label=f"Default {prov.title()} Key (from .env)",
                provider=prov,
                model=model,
                base_url=base_url,
                enabled=True
            )
            new_key.set_secret(env_key)
            db.add(new_key)
            db.commit()
            db.refresh(new_key)
            healthy.append(new_key)

        return healthy

    def _auto_discover_new_model(self, key: AIKey, db: Optional[Session] = None) -> Optional[str]:
        """
        Dynamically queries the provider's /models endpoint on the fly,
        strictly intersecting with PROVIDER_ALLOWLISTS to ensure only pre-vetted,
        economical chat models are selected (preventing quiet paid model traps).
        """
        provider = key.provider.lower().strip()
        allowlist = PROVIDER_ALLOWLISTS.get(provider, [])
        base_url = key.base_url or PROVIDER_PRESETS.get(provider, {}).get("base_url", "")

        if base_url:
            models_endpoint = f"{base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {key.api_key}"}

            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(models_endpoint, headers=headers)
                    if res.status_code == 200:
                        data = res.json().get("data", [])
                        available_ids = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
                        
                        # Strict Allowlist Selection: Pick the first allowlisted model present on endpoint
                        for vetted_model in allowlist:
                            if vetted_model in available_ids and vetted_model != key.model:
                                logger.info(f"Self-Healing: Selected allowlisted model '{vetted_model}' for {provider}")
                                self._update_key_model(key, vetted_model, db)
                                return vetted_model
            except Exception as e:
                logger.warning(f"Allowlist model discovery query failed on {provider}: {e}")

        # Fallback strictly within allowlist
        for fallback in allowlist:
            if fallback != key.model:
                self._update_key_model(key, fallback, db)
                return fallback

        return None

    def _update_key_model(self, key: AIKey, new_model: str, db: Optional[Session] = None):
        key.model = new_model
        if db:
            db.commit()

    def _execute_single_key(self, key: AIKey, prompt: str, db: Optional[Session] = None) -> str:
        provider = key.provider.lower().strip()
        model = key.model or PROVIDER_PRESETS.get(provider, {}).get("default_model", "gemini-2.5-flash")

        # 1. Google Gemini
        if provider == "gemini":
            from google import genai
            if key.api_key not in self._gemini_clients:
                self._gemini_clients[key.api_key] = genai.Client(api_key=key.api_key)
            client = self._gemini_clients[key.api_key]

            try:
                resp = client.models.generate_content(
                    model=model or "gemini-2.5-flash",
                    contents=prompt
                )
                return resp.text.strip()
            except Exception as e:
                err_text = str(e).lower()
                if "not_found" in err_text or "deprecated" in err_text or "404" in err_text:
                    fallback_model = "gemini-1.5-flash" if model != "gemini-1.5-flash" else "gemini-2.5-flash"
                    logger.warning(f"Gemini model {model} failed. Auto-switching to fallback: {fallback_model}")
                    self._update_key_model(key, fallback_model, db)
                    resp = client.models.generate_content(model=fallback_model, contents=prompt)
                    return resp.text.strip()
                raise e

        # 2. OpenAI-compatible providers
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
            
            # Rate limit handling (HTTP 429 / 403 quota)
            if res.status_code == 429:
                retry_header = res.headers.get("retry-after")
                cooldown_sec = int(retry_header) if retry_header and retry_header.isdigit() else 900
                raise RateLimitException(f"HTTP 429 Too Many Requests from {provider}", cooldown_seconds=cooldown_sec)

            if res.status_code == 403 and ("quota" in res.text.lower() or "limit" in res.text.lower()):
                raise RateLimitException(f"HTTP 403 Quota Exceeded from {provider}", cooldown_seconds=1800)

            # DEPRECATION / NOT FOUND SELF-HEALING (HTTP 404, 410, model_not_found, gone)
            if res.status_code in (404, 410) or any(x in res.text.lower() for x in ["model_not_found", "deprecated", "end of life", "no longer available"]):
                logger.warning(f"Model '{model}' on {provider} is deprecated or not found (HTTP {res.status_code}). Triggering auto-discovery...")
                new_model = self._auto_discover_new_model(key, db)
                if new_model and new_model != model:
                    logger.info(f"Retrying request with newly auto-selected model: '{new_model}'")
                    payload["model"] = new_model
                    retry_res = http_client.post(target_url, headers=headers, json=payload)
                    if retry_res.status_code == 200:
                        data = retry_res.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "").strip()

            if res.status_code != 200:
                raise Exception(f"{provider.upper()} API returned status {res.status_code}: {res.text[:300]}")

            data = res.json()
            choices = data.get("choices", [])
            if not choices:
                raise Exception(f"Empty choices returned by {provider}")

            content = choices[0].get("message", {}).get("content", "").strip()
            return content

    def call_with_failover(self, prompt: str, db: Session) -> Tuple[Optional[str], Optional[str]]:
        tried_key_ids = set()

        while True:
            healthy_keys = self.get_healthy_keys(db)
            available = [k for k in healthy_keys if k.id not in tried_key_ids]

            if not available:
                logger.warning("All available keys in the pool have been exhausted or are in cooldown.")
                return None, None

            selected_key = available[self._round_robin_idx % len(available)]
            self._round_robin_idx += 1
            tried_key_ids.add(selected_key.id)

            selected_key.total_requests += 1
            selected_key.last_used_at = datetime.now(timezone.utc)

            try:
                logger.info(f"Routing AI request to key #{selected_key.id} [{selected_key.label}] ({selected_key.provider}:{selected_key.model})")
                text = self._execute_single_key(selected_key, prompt, db=db)
                selected_key.successful_requests += 1
                selected_key.last_error_message = ""
                db.commit()
                return text, f"{selected_key.label} ({selected_key.provider}:{selected_key.model})"

            except RateLimitException as rle:
                logger.warning(f"Rate limit hit on key #{selected_key.id} [{selected_key.label}]: {rle}. Moving to cooldown for {rle.cooldown_seconds}s and failing over...")
                selected_key.is_in_cooldown = True
                selected_key.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=rle.cooldown_seconds)
                selected_key.rate_limit_hits += 1
                selected_key.last_error_message = str(rle)
                db.commit()
                continue

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "resource_exhausted" in err_msg.lower() or "quota" in err_msg.lower():
                    logger.warning(f"Quota error on key #{selected_key.id} [{selected_key.label}]: {err_msg}. Moving to cooldown and failing over...")
                    selected_key.is_in_cooldown = True
                    selected_key.cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                    selected_key.rate_limit_hits += 1
                    selected_key.last_error_message = err_msg
                    db.commit()
                    continue

                logger.error(f"Error on key #{selected_key.id} [{selected_key.label}]: {err_msg}. Failing over to next key...")
                selected_key.last_error_message = err_msg
                db.commit()
                continue

    def test_key(self, key: AIKey) -> Dict[str, Any]:
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
