from pathlib import Path

from pytest import MonkeyPatch

from subloom.config import Settings
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
    ) -> SubtitleDocument:
        assert source_language == "en"
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
            language="zh-CN",
        )


def test_pipeline_uses_embedded_text_subtitle_and_preserves_timing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()
    output = tmp_path / "movie.zh-CN.srt"
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

    result = pipeline.process(video, output, confirm_transcription=lambda: False)

    rendered = parse_srt(output.read_text(encoding="utf-8"))
    assert result.source is SubtitleSource.EMBEDDED
    assert rendered.cues[0].text == "Translated line"
    assert rendered.cues[0].start_ms == 1_000
    assert rendered.cues[0].end_ms == 2_000
