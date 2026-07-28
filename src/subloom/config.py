from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from subloom.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr | None = None
    openai_translation_model: str = "gpt-5.6-luna"
    openai_transcription_model: str = "whisper-1"

    opensubtitles_api_key: SecretStr | None = None
    opensubtitles_username: str | None = None
    opensubtitles_password: SecretStr | None = None
    opensubtitles_languages: str = "en"

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    translation_batch_size: int = 40
    audio_chunk_seconds: int = 600

    @property
    def subtitle_languages(self) -> list[str]:
        return [value.strip() for value in self.opensubtitles_languages.split(",") if value.strip()]

    def require_openai_key(self) -> str:
        if self.openai_api_key is None:
            raise ConfigurationError("OPENAI_API_KEY is required for translation or transcription")
        return self.openai_api_key.get_secret_value()

    def require_opensubtitles_key(self) -> str:
        if self.opensubtitles_api_key is None:
            raise ConfigurationError("OPENSUBTITLES_API_KEY is required to search OpenSubtitles")
        return self.opensubtitles_api_key.get_secret_value()

    @classmethod
    def from_project_env(cls, project_dir: Path | None = None) -> "Settings":
        env_file = (project_dir or Path.cwd()) / ".env"
        return cls(_env_file=env_file if env_file.exists() else None)  # type: ignore[call-arg]
