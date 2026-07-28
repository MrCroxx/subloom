from pathlib import Path

from pytest import MonkeyPatch

from subloom.config import Settings
from subloom.languages import TargetLanguage
from subloom.models import (
    MediaInfo,
    SubtitleCue,
    SubtitleDocument,
    SubtitleSource,
    SubtitleStream,
)
from subloom.pipeline import SubtitlePipeline
from subloom.subtitles import parse_srt


class FakeMediaTool:
    def __init__(self, media: MediaInfo, stream: SubtitleStream | None) -> None:
        self.media = media
        self.stream = stream

    def ensure_available(self) -> None:
        pass

    def probe(self, *_: object, **__: object) -> MediaInfo:
        return self.media

    def select_subtitle_stream(self, *_: object, **__: object) -> SubtitleStream | None:
        return self.stream

    def extract_subtitle(self, _: Path, __: SubtitleStream, output: Path) -> None:
        output.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
            encoding="utf-8",
        )


class FakeOpenAIService:
    def translate(
        self,
        document: SubtitleDocument,
        _: MediaInfo,
        source_language: str | None,
        target_language: TargetLanguage,
    ) -> SubtitleDocument:
        assert source_language == "en"
        assert target_language.tag == "fr"
        cue = document.cues[0]
        return SubtitleDocument(
            cues=(
                SubtitleCue(
                    index=cue.index,
                    start_ms=cue.start_ms,
                    end_ms=cue.end_ms,
                    text="Translated line",
                ),
            ),
            language=target_language.tag,
        )


def test_pipeline_uses_embedded_text_subtitle_and_preserves_timing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()
    output = tmp_path / "movie.fr.srt"
    stream = SubtitleStream(index=2, codec="subrip", language="en")
    media = MediaInfo(
        path=video,
        title="Movie",
        year=2020,
        duration_ms=10_000,
        subtitle_streams=(stream,),
    )
    pipeline = SubtitlePipeline(Settings(openai_api_key="test-key"))
    pipeline.media_tool = FakeMediaTool(media, stream)  # type: ignore[assignment]
    monkeypatch.setattr(pipeline, "_openai_service", lambda: FakeOpenAIService())

    result = pipeline.process(
        video,
        output,
        target_language=TargetLanguage.parse("French"),
        confirm_transcription=lambda: False,
    )

    rendered = parse_srt(output.read_text(encoding="utf-8"))
    assert result.source is SubtitleSource.EMBEDDED
    assert result.target_language == "fr"
    assert rendered.cues[0].text == "Translated line"
    assert rendered.cues[0].start_ms == 1_000
    assert rendered.cues[0].end_ms == 2_000


def test_pipeline_reuses_an_embedded_target_language_subtitle(tmp_path: Path) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()
    output = tmp_path / "movie.fr.srt"
    stream = SubtitleStream(index=2, codec="subrip", language="fra")
    media = MediaInfo(
        path=video,
        title="Movie",
        year=2020,
        duration_ms=10_000,
        subtitle_streams=(stream,),
    )
    pipeline = SubtitlePipeline(Settings())
    pipeline.media_tool = FakeMediaTool(media, stream)  # type: ignore[assignment]

    result = pipeline.process(
        video,
        output,
        target_language=TargetLanguage.parse("fr"),
        confirm_transcription=lambda: False,
    )

    assert result.source is SubtitleSource.EXISTING_TARGET
    assert result.source_language == "fra"
    assert result.target_language == "fr"
    assert parse_srt(output.read_text(encoding="utf-8")).cues[0].text == "Hello"
