from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

CHINESE_LANGUAGE_CODES = frozenset({"zh", "zho", "chi", "zh-cn", "zh-hans", "cmn"})


def is_chinese_language(language: str | None) -> bool:
    return language is not None and language.casefold() in CHINESE_LANGUAGE_CODES


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("cue index must be positive")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("cue timestamps must be ordered and non-negative")
        if not self.text.strip():
            raise ValueError("cue text must not be empty")


@dataclass(frozen=True, slots=True)
class SubtitleDocument:
    cues: tuple[SubtitleCue, ...]
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.cues:
            raise ValueError("subtitle document must contain at least one cue")


@dataclass(frozen=True, slots=True)
class SubtitleStream:
    index: int
    codec: str
    language: str | None = None
    title: str | None = None
    is_default: bool = False
    is_forced: bool = False


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    title: str
    year: int | None
    duration_ms: int
    subtitle_streams: tuple[SubtitleStream, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OpenSubtitleCandidate:
    file_id: int
    file_name: str
    language: str
    release: str | None
    download_count: int
    moviehash_match: bool


class SubtitleSource(StrEnum):
    EMBEDDED = "embedded"
    OPENSUBTITLES = "opensubtitles"
    TRANSCRIPTION = "transcription"
    EXISTING_CHINESE = "existing_chinese"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    output_path: Path
    source: SubtitleSource
    source_language: str | None
    cue_count: int
    warning: str | None = None
