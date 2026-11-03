class JobPulseError(Exception):
    """Base exception for all JobPulse domain errors."""
    pass

class RateLimitError(JobPulseError):
    """Raised when an external API provider rate limits a request."""
    def __init__(self, message: str, cooldown_seconds: int = 900):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds

class QuotaExceededError(RateLimitError):
    """Raised when an API provider quota has been exhausted (daily/monthly)."""
    def __init__(self, message: str, cooldown_seconds: int = 86400):
        super().__init__(message, cooldown_seconds=cooldown_seconds)

class ModelNotFoundError(JobPulseError):
    """Raised when an LLM model ID is deprecated, retired, or not found."""
    pass

class ConnectorError(JobPulseError):
    """Raised when an external job source fails to respond or parse."""
    pass

class AutofillError(JobPulseError):
    """Raised when browser automation encounters an unexpected state or unmappable field."""
    pass

