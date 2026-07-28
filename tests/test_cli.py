from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from subloom.cli import app
from subloom.models import ProcessResult, SubtitleSource
from subloom.pipeline import SubtitlePipeline

runner = CliRunner()


def test_cli_normalizes_target_language_in_the_default_output_path(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()
    captured: dict[str, Any] = {}

    def fake_process(
        _: SubtitlePipeline,
        video_path: Path,
        output_path: Path,
        **kwargs: Any,
    ) -> ProcessResult:
        captured["video_path"] = video_path
        captured["output_path"] = output_path
        captured.update(kwargs)
        return ProcessResult(
            output_path=output_path,
            source=SubtitleSource.EMBEDDED,
            source_language="en",
            target_language="pt-BR",
            cue_count=1,
        )

    monkeypatch.setattr(SubtitlePipeline, "process", fake_process)

    result = runner.invoke(
        app,
        [str(video), "--target-language", "Brazilian Portuguese"],
    )

    assert result.exit_code == 0
    assert captured["output_path"] == tmp_path / "movie.pt-BR.srt"
    assert captured["target_language"].tag == "pt-BR"


def test_cli_keeps_simplified_chinese_as_the_default_target(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()
    captured: dict[str, Any] = {}

    def fake_process(
        _: SubtitlePipeline,
        video_path: Path,
        output_path: Path,
        **kwargs: Any,
    ) -> ProcessResult:
        captured["output_path"] = output_path
        captured.update(kwargs)
        return ProcessResult(
            output_path=output_path,
            source=SubtitleSource.EMBEDDED,
            source_language="en",
            target_language="zh-CN",
            cue_count=1,
        )

    monkeypatch.setattr(SubtitlePipeline, "process", fake_process)

    result = runner.invoke(app, [str(video)])

    assert result.exit_code == 0
    assert captured["output_path"] == tmp_path / "movie.zh-CN.srt"
    assert captured["target_language"].tag == "zh-CN"


def test_cli_rejects_an_unknown_target_language(tmp_path: Path) -> None:
    video = tmp_path / "movie.mkv"
    video.touch()

    result = runner.invoke(app, [str(video), "--target-language", "not a real language"])

    assert result.exit_code == 2
    assert "unknown target language" in " ".join(result.output.split())
