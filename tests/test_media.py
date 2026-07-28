from pathlib import Path

from subloom.media import MediaTool, infer_title_and_year
from subloom.models import MediaInfo, SubtitleStream


def test_infer_title_and_year_removes_release_metadata() -> None:
    title, year = infer_title_and_year(Path("The.Matrix.1999.1080p.BluRay.x265.mkv"))

    assert title == "The Matrix"
    assert year == 1999


def test_select_subtitle_prefers_existing_chinese() -> None:
    media = MediaInfo(
        path=Path("movie.mkv"),
        title="Movie",
        year=None,
        duration_ms=1_000,
        subtitle_streams=(
            SubtitleStream(index=2, codec="subrip", language="en", is_default=True),
            SubtitleStream(index=3, codec="ass", language="zho"),
        ),
    )

    selected = MediaTool().select_subtitle_stream(media, preferred_language="en")

    assert selected is not None
    assert selected.index == 3


def test_select_subtitle_ignores_image_based_streams() -> None:
    media = MediaInfo(
        path=Path("movie.mkv"),
        title="Movie",
        year=None,
        duration_ms=1_000,
        subtitle_streams=(SubtitleStream(index=2, codec="hdmv_pgs_subtitle", language="en"),),
    )

    assert MediaTool().select_subtitle_stream(media) is None
