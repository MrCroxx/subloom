import re
from collections.abc import Iterable
from pathlib import Path

from charset_normalizer import from_bytes

from subloom.models import SubtitleCue, SubtitleDocument

TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{1,3}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,3}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)


def parse_timestamp(value: str) -> int:
    hours, minutes, rest = value.replace(".", ",").split(":")
    seconds, milliseconds = rest.split(",")
    return int(hours) * 3_600_000 + int(minutes) * 60_000 + int(seconds) * 1_000 + int(milliseconds)


def format_timestamp(value_ms: int) -> str:
    hours, remainder = divmod(value_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt(content: str, language: str | None = None) -> SubtitleDocument:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = re.split(r"\n{2,}", normalized.strip())
    cues: list[SubtitleCue] = []

    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue

        timestamp_position = next(
            (position for position, line in enumerate(lines[:2]) if TIMESTAMP_RE.match(line)),
            None,
        )
        if timestamp_position is None:
            continue

        match = TIMESTAMP_RE.match(lines[timestamp_position])
        assert match is not None
        text = "\n".join(lines[timestamp_position + 1 :]).strip()
        if not text:
            continue

        cues.append(
            SubtitleCue(
                index=len(cues) + 1,
                start_ms=parse_timestamp(match.group("start")),
                end_ms=parse_timestamp(match.group("end")),
                text=text,
            )
        )

    return SubtitleDocument(cues=tuple(cues), language=language)


def render_srt(document: SubtitleDocument) -> str:
    blocks = [
        "\n".join(
            (
                str(position),
                f"{format_timestamp(cue.start_ms)} --> {format_timestamp(cue.end_ms)}",
                cue.text.strip(),
            )
        )
        for position, cue in enumerate(document.cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def read_srt(path: Path, language: str | None = None) -> SubtitleDocument:
    raw = path.read_bytes()
    detected = from_bytes(raw).best()
    if detected is None:
        raise ValueError(f"cannot detect subtitle encoding: {path}")
    return parse_srt(str(detected), language=language)


def write_srt(path: Path, document: SubtitleDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_srt(document), encoding="utf-8", newline="\n")


def replace_texts(
    document: SubtitleDocument,
    texts: Iterable[str],
    target_language: str,
) -> SubtitleDocument:
    translated = list(texts)
    if len(translated) != len(document.cues):
        raise ValueError("translated cue count does not match source cue count")

    cues = tuple(
        SubtitleCue(
            index=cue.index,
            start_ms=cue.start_ms,
            end_ms=cue.end_ms,
            text=text.strip(),
        )
        for cue, text in zip(document.cues, translated, strict=True)
    )
    return SubtitleDocument(cues=cues, language=target_language)
