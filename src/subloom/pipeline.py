from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from subloom.config import Settings
from subloom.errors import (
    ConfigurationError,
    SubtitleNotFoundError,
    UserCancelledError,
)
from subloom.media import MediaTool
from subloom.models import (
    MediaInfo,
    ProcessResult,
    SubtitleDocument,
    SubtitleSource,
    is_chinese_language,
)
from subloom.openai_service import OpenAIService
from subloom.opensubtitles import OpenSubtitlesClient
from subloom.subtitles import read_srt, write_srt

ProgressCallback = Callable[[str], None]
ConfirmationCallback = Callable[[], bool]


class SubtitlePipeline:
    def __init__(self, settings: Settings, progress: ProgressCallback | None = None) -> None:
        self.settings = settings
        self.progress = progress or (lambda _: None)
        self.media_tool = MediaTool(settings.ffmpeg_path, settings.ffprobe_path)

    def process(
        self,
        video_path: Path,
        output_path: Path,
        *,
        title: str | None = None,
        year: int | None = None,
        source_language: str | None = None,
        embedded_stream_index: int | None = None,
        search_opensubtitles: bool = True,
        confirm_transcription: ConfirmationCallback | None = None,
    ) -> ProcessResult:
        self.media_tool.ensure_available()
        media = self.media_tool.probe(video_path, title=title, year=year)
        self.progress(
            f"Detected: {media.title} ({media.year or 'unknown year'}), "
            f"{media.duration_ms / 60_000:.1f} minutes"
        )

        with TemporaryDirectory(prefix="subloom-") as temporary:
            work_dir = Path(temporary)
            stream = self.media_tool.select_subtitle_stream(
                media,
                preferred_language=source_language,
                stream_index=embedded_stream_index,
            )
            if embedded_stream_index is not None and stream is None:
                raise SubtitleNotFoundError(
                    f"embedded stream {embedded_stream_index} is not a supported text subtitle"
                )

            if stream is not None:
                self.progress(
                    f"Using embedded subtitle stream {stream.index} "
                    f"({stream.language or 'unknown'}, {stream.codec})"
                )
                source_path = work_dir / "embedded.srt"
                self.media_tool.extract_subtitle(media.path, stream, source_path)
                document = read_srt(source_path, language=stream.language)
                if is_chinese_language(stream.language):
                    write_srt(output_path, document)
                    return ProcessResult(
                        output_path=output_path,
                        source=SubtitleSource.EXISTING_CHINESE,
                        source_language=stream.language,
                        cue_count=len(document.cues),
                    )
                return self._translate_and_write(
                    document,
                    media,
                    output_path,
                    SubtitleSource.EMBEDDED,
                    source_language or stream.language,
                )

            if search_opensubtitles and self.settings.opensubtitles_api_key is not None:
                online_document, language, hash_match = self._from_opensubtitles(media, work_dir)
                if online_document is not None:
                    result = self._translate_and_write(
                        online_document,
                        media,
                        output_path,
                        SubtitleSource.OPENSUBTITLES,
                        source_language or language,
                    )
                    if not hash_match:
                        return ProcessResult(
                            output_path=result.output_path,
                            source=result.source,
                            source_language=result.source_language,
                            cue_count=result.cue_count,
                            warning=(
                                "OpenSubtitles matched by title rather than movie hash; "
                                "verify synchronization against the video"
                            ),
                        )
                    return result
            elif search_opensubtitles:
                self.progress("Skipping OpenSubtitles: OPENSUBTITLES_API_KEY is not configured")

            self.progress("No usable embedded or OpenSubtitles subtitle was found")
            if confirm_transcription is None or not confirm_transcription():
                raise UserCancelledError("speech-to-text fallback was not approved")

            self.progress("Transcribing audio with timestamped speech segments")
            service = self._openai_service()
            document = service.transcribe(
                media,
                self.media_tool,
                work_dir,
                chunk_seconds=self.settings.audio_chunk_seconds,
                language=source_language,
            )
            return self._translate_and_write(
                document,
                media,
                output_path,
                SubtitleSource.TRANSCRIPTION,
                source_language or document.language,
                service=service,
            )

    def _from_opensubtitles(
        self,
        media: MediaInfo,
        work_dir: Path,
    ) -> tuple[SubtitleDocument | None, str | None, bool]:
        self.progress("Searching OpenSubtitles")
        password = (
            self.settings.opensubtitles_password.get_secret_value()
            if self.settings.opensubtitles_password is not None
            else None
        )
        try:
            with OpenSubtitlesClient(
                api_key=self.settings.require_opensubtitles_key(),
                username=self.settings.opensubtitles_username,
                password=password,
            ) as client:
                candidates = client.search(media, self.settings.subtitle_languages)
                for candidate in candidates[:3]:
                    self.progress(
                        f"Trying OpenSubtitles file {candidate.file_name} ({candidate.language})"
                    )
                    destination = work_dir / f"opensubtitles-{candidate.file_id}.srt"
                    try:
                        client.download_srt(candidate, destination)
                        return (
                            read_srt(destination, language=candidate.language),
                            candidate.language,
                            candidate.moviehash_match,
                        )
                    except (
                        SubtitleNotFoundError,
                        ValueError,
                        UnicodeError,
                        httpx.HTTPError,
                    ) as error:
                        self.progress(f"Rejected subtitle candidate: {error}")
        except (ConfigurationError, httpx.HTTPError) as error:
            self.progress(f"OpenSubtitles unavailable: {error}")
        return None, None, False

    def _translate_and_write(
        self,
        document: SubtitleDocument,
        media: MediaInfo,
        output_path: Path,
        source: SubtitleSource,
        source_language: str | None,
        service: OpenAIService | None = None,
    ) -> ProcessResult:
        self.progress(f"Translating {len(document.cues)} cues into Simplified Chinese")
        translated = (service or self._openai_service()).translate(
            document,
            media,
            source_language=source_language,
        )
        write_srt(output_path, translated)
        return ProcessResult(
            output_path=output_path,
            source=source,
            source_language=source_language,
            cue_count=len(translated.cues),
        )

    def _openai_service(self) -> OpenAIService:
        return OpenAIService(
            api_key=self.settings.require_openai_key(),
            translation_model=self.settings.openai_translation_model,
            transcription_model=self.settings.openai_transcription_model,
            batch_size=self.settings.translation_batch_size,
        )
