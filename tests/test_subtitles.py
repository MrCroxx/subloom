import pytest

from subloom.models import SubtitleCue, SubtitleDocument
from subloom.subtitles import parse_srt, render_srt, replace_texts


def test_parse_and_render_srt_preserves_timestamps() -> None:
    source = """7
00:00:01,250 --> 00:00:03,500
Hello.

8
00:01:02.000 --> 00:01:04.125 position:50%
Second line.
Still here.
"""

    document = parse_srt(source, language="en")

    assert [(cue.start_ms, cue.end_ms) for cue in document.cues] == [
        (1_250, 3_500),
        (62_000, 64_125),
    ]
    assert document.cues[1].text == "Second line.\nStill here."
    assert render_srt(document).startswith("1\n00:00:01,250 --> 00:00:03,500")


def test_replace_texts_changes_only_text_and_language() -> None:
    source = SubtitleDocument(
        cues=(SubtitleCue(index=1, start_ms=100, end_ms=900, text="Hello"),),
        language="en",
    )

    translated = replace_texts(source, ["Translated line"], target_language="fr")

    assert translated.language == "fr"
    assert translated.cues[0].text == "Translated line"
    assert translated.cues[0].start_ms == 100
    assert translated.cues[0].end_ms == 900


def test_replace_texts_rejects_a_different_cue_count() -> None:
    source = SubtitleDocument(cues=(SubtitleCue(index=1, start_ms=100, end_ms=900, text="Hello"),))

    with pytest.raises(ValueError, match="cue count"):
        replace_texts(source, [], target_language="fr")
