import json
from pathlib import Path

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from subloom.errors import TranslationError
from subloom.languages import TargetLanguage
from subloom.media import MediaTool
from subloom.models import MediaInfo, SubtitleCue, SubtitleDocument
from subloom.subtitles import replace_texts


class TranslatedCue(BaseModel):
    cue_id: int
    text: str = Field(min_length=1)


class TranslationBatch(BaseModel):
    cues: list[TranslatedCue]


class OpenAIService:
    def __init__(
        self,
        api_key: str,
        translation_model: str,
        transcription_model: str,
        batch_size: int = 40,
    ) -> None:
        self.client = OpenAI(api_key=api_key, max_retries=2)
        self.translation_model = translation_model
        self.transcription_model = transcription_model
        self.batch_size = batch_size

    def translate(
        self,
        document: SubtitleDocument,
        media: MediaInfo,
        source_language: str | None,
        target_language: TargetLanguage,
    ) -> SubtitleDocument:
        translated_by_id: dict[int, str] = {}
        cues = document.cues

        for offset in range(0, len(cues), self.batch_size):
            batch = cues[offset : offset + self.batch_size]
            before = cues[max(0, offset - 3) : offset]
            after = cues[offset + len(batch) : offset + len(batch) + 3]
            try:
                response = self.client.responses.parse(
                    model=self.translation_model,
                    input=[
                        {
                            "role": "system",
                            "content": self._translation_instructions(
                                media=media,
                                source_language=source_language,
                                target_language=target_language,
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "previous_context": self._serialize_cues(before),
                                    "cues_to_translate": self._serialize_cues(batch),
                                    "following_context": self._serialize_cues(after),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    text_format=TranslationBatch,
                )
            except OpenAIError as error:
                raise TranslationError(f"OpenAI translation failed: {error}") from error
            parsed = response.output_parsed
            if parsed is None:
                raise TranslationError("OpenAI returned no parsed translation")
            expected = {cue.index for cue in batch}
            actual = {cue.cue_id for cue in parsed.cues}
            if actual != expected or len(parsed.cues) != len(batch):
                raise TranslationError(
                    f"translated cue IDs do not match source: expected {sorted(expected)}, "
                    f"got {sorted(actual)}"
                )
            translated_by_id.update({cue.cue_id: cue.text for cue in parsed.cues})

        return replace_texts(
            document,
            (translated_by_id[cue.index] for cue in cues),
            target_language=target_language.tag,
        )

    def transcribe(
        self,
        media: MediaInfo,
        media_tool: MediaTool,
        work_dir: Path,
        chunk_seconds: int,
        language: str | None = None,
    ) -> SubtitleDocument:
        cues: list[SubtitleCue] = []
        duration_seconds = (media.duration_ms + 999) // 1_000
        detected_language = language

        for start_seconds in range(0, duration_seconds, chunk_seconds):
            current_duration = min(chunk_seconds, duration_seconds - start_seconds)
            audio_path = work_dir / f"audio-{start_seconds:08d}.ogg"
            media_tool.extract_audio_chunk(
                media.path,
                audio_path,
                start_seconds=start_seconds,
                duration_seconds=current_duration,
            )
            with audio_path.open("rb") as audio:
                try:
                    if language:
                        transcription = self.client.audio.transcriptions.create(
                            model=self.transcription_model,
                            file=audio,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"],
                            language=language,
                        )
                    else:
                        transcription = self.client.audio.transcriptions.create(
                            model=self.transcription_model,
                            file=audio,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"],
                        )
                except OpenAIError as error:
                    raise TranslationError(f"OpenAI transcription failed: {error}") from error

            response_language = getattr(transcription, "language", None)
            if isinstance(response_language, str):
                detected_language = response_language
            for segment in getattr(transcription, "segments", ()) or ():
                text = self._field(segment, "text")
                start = self._field(segment, "start")
                end = self._field(segment, "end")
                if not isinstance(text, str) or not text.strip():
                    continue
                if not isinstance(start, int | float) or not isinstance(end, int | float):
                    continue
                start_ms = start_seconds * 1_000 + round(start * 1_000)
                end_ms = start_seconds * 1_000 + round(end * 1_000)
                if end_ms <= start_ms:
                    continue
                cues.append(
                    SubtitleCue(
                        index=len(cues) + 1,
                        start_ms=start_ms,
                        end_ms=min(end_ms, media.duration_ms),
                        text=text.strip(),
                    )
                )
            audio_path.unlink(missing_ok=True)

        if not cues:
            raise TranslationError("transcription returned no timestamped speech segments")
        return SubtitleDocument(cues=tuple(cues), language=detected_language)

    @staticmethod
    def _field(value: object, name: str) -> object:
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    @staticmethod
    def _serialize_cues(cues: tuple[SubtitleCue, ...]) -> list[dict[str, object]]:
        return [{"cue_id": cue.index, "text": cue.text} for cue in cues]

    @staticmethod
    def _translation_instructions(
        media: MediaInfo,
        source_language: str | None,
        target_language: TargetLanguage,
    ) -> str:
        year = str(media.year) if media.year is not None else "unknown"
        language = source_language or "auto-detected"
        return f"""You are a professional film subtitle translator and editor.
Translate only cues_to_translate into natural {target_language.display_name}.
Movie title: {media.title}
Release year: {year}
Source language: {language}
Target language: {target_language.display_name} ({target_language.tag})

Use film context, characterization, genre conventions, and adjacent cues to resolve ambiguity.
Keep dialogue concise enough to read on screen. Preserve meaningful line breaks, speaker markers,
italics tags, and sound-description brackets. Use established target-language renderings for
names and culturally specific terms when they exist. Return every cue exactly once with the
original cue_id.
Never merge, split, reorder, omit, or invent cues. Context cues are reference only and must not
be returned."""
