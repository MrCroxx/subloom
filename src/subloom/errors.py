class SubloomError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(SubloomError):
    """Raised when required configuration is missing or invalid."""


class ExternalToolError(SubloomError):
    """Raised when FFmpeg or FFprobe fails."""


class SubtitleNotFoundError(SubloomError):
    """Raised when no usable subtitle source can be found."""


class UserCancelledError(SubloomError):
    """Raised when the user declines the transcription fallback."""


class TranslationError(SubloomError):
    """Raised when translated cues fail structural validation."""
