import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from subloom.errors import ExternalToolError
from subloom.models import MediaInfo, SubtitleStream, is_chinese_language

TEXT_SUBTITLE_CODECS = frozenset({"ass", "mov_text", "ssa", "subrip", "text", "ttml", "webvtt"})
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
RELEASE_NOISE_RE = re.compile(
    r"(?ix)\b(?:2160p|1080p|720p|480p|bluray|bdrip|webrip|web-dl|hdtv|"
    r"x26[45]|h\.26[45]|hevc|av1|remux|hdr10?|dv|dts|aac).*"
)


def infer_title_and_year(path: Path) -> tuple[str, int | None]:
    stem = path.stem.replace(".", " ").replace("_", " ")
    year_match = YEAR_RE.search(stem)
    year = int(year_match.group(1)) if year_match else None
    if year_match:
        stem = stem[: year_match.start()]
    stem = RELEASE_NOISE_RE.sub("", stem)
    title = re.sub(r"\s+", " ", stem).strip(" -[]()")
    return title or path.stem, year


class MediaTool:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def ensure_available(self) -> None:
        missing = [
            tool for tool in (self.ffmpeg_path, self.ffprobe_path) if shutil.which(tool) is None
        ]
        if missing:
            raise ExternalToolError(f"required executable not found: {', '.join(missing)}")

    def probe(self, path: Path, title: str | None = None, year: int | None = None) -> MediaInfo:
        if not path.is_file():
            raise ExternalToolError(f"video file does not exist: {path}")
        payload = self._run_json(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ]
        )
        inferred_title, inferred_year = infer_title_and_year(path)
        format_data = payload.get("format", {})
        duration_ms = round(float(format_data.get("duration", 0)) * 1_000)
        if duration_ms <= 0:
            raise ExternalToolError("FFprobe did not return a valid media duration")

        streams: list[SubtitleStream] = []
        for stream in payload.get("streams", []):
            if stream.get("codec_type") != "subtitle":
                continue
            tags = stream.get("tags", {})
            disposition = stream.get("disposition", {})
            streams.append(
                SubtitleStream(
                    index=int(stream["index"]),
                    codec=str(stream.get("codec_name", "unknown")),
                    language=tags.get("language"),
                    title=tags.get("title"),
                    is_default=bool(disposition.get("default")),
                    is_forced=bool(disposition.get("forced")),
                )
            )

        return MediaInfo(
            path=path,
            title=title or inferred_title,
            year=year if year is not None else inferred_year,
            duration_ms=duration_ms,
            subtitle_streams=tuple(streams),
        )

    def select_subtitle_stream(
        self,
        media: MediaInfo,
        preferred_language: str | None = None,
        stream_index: int | None = None,
    ) -> SubtitleStream | None:
        text_streams = [
            stream for stream in media.subtitle_streams if stream.codec in TEXT_SUBTITLE_CODECS
        ]
        if stream_index is not None:
            return next((stream for stream in text_streams if stream.index == stream_index), None)

        def rank(stream: SubtitleStream) -> tuple[int, int, int, int]:
            language_match = int(
                preferred_language is not None
                and stream.language is not None
                and stream.language.casefold() == preferred_language.casefold()
            )
            return (
                int(is_chinese_language(stream.language)),
                language_match,
                int(stream.is_default),
                -stream.index,
            )

        return max(text_streams, key=rank, default=None)

    def extract_subtitle(self, media_path: Path, stream: SubtitleStream, output: Path) -> None:
        self._run(
            [
                self.ffmpeg_path,
                "-v",
                "error",
                "-y",
                "-i",
                str(media_path),
                "-map",
                f"0:{stream.index}",
                "-c:s",
                "srt",
                str(output),
            ]
        )

    def extract_audio_chunk(
        self,
        media_path: Path,
        output: Path,
        start_seconds: int,
        duration_seconds: int,
    ) -> None:
        self._run(
            [
                self.ffmpeg_path,
                "-v",
                "error",
                "-y",
                "-ss",
                str(start_seconds),
                "-i",
                str(media_path),
                "-t",
                str(duration_seconds),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                str(output),
            ]
        )

    def _run_json(self, command: list[str]) -> dict[str, Any]:
        output = self._run(command)
        try:
            value = json.loads(output)
        except json.JSONDecodeError as error:
            raise ExternalToolError("FFprobe returned invalid JSON") from error
        if not isinstance(value, dict):
            raise ExternalToolError("FFprobe returned an unexpected JSON value")
        return value

    @staticmethod
    def _run(command: list[str]) -> str:
        try:
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise ExternalToolError(f"failed to execute {command[0]}: {error}") from error
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip() or "unknown error"
            raise ExternalToolError(f"{command[0]} failed: {detail}")
        return process.stdout
