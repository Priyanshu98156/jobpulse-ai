import re
import logging
import structlog
from typing import Any, MutableMapping

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?[0-9]{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}")
SENSITIVE_KEYS = {"api_key", "password", "secret", "token", "resume_text", "prompt", "cover_letter"}

def redact_pii_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """
    Structlog processor that masks API keys, secrets, emails, and phone numbers from logs.
    """
    for key, value in list(event_dict.items()):
        key_lower = key.lower()
        if any(s in key_lower for s in SENSITIVE_KEYS):
            event_dict[key] = "[REDACTED]"
        elif isinstance(value, str):
            # Redact email addresses
            redacted = EMAIL_REGEX.sub("[EMAIL_REDACTED]", value)
            # Redact phone patterns
            redacted = PHONE_REGEX.sub("[PHONE_REDACTED]", redacted)
            event_dict[key] = redacted
    return event_dict

def setup_logging(level: int = logging.INFO):
    """Configures structured logging with PII redaction."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_pii_processor,
            structlog.dev.ConsoleRenderer(colors=False)
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )

