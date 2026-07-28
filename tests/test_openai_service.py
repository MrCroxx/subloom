from pathlib import Path

from subloom.languages import TargetLanguage
from subloom.models import MediaInfo
from subloom.openai_service import OpenAIService


def test_translation_instructions_use_the_requested_target_language() -> None:
    media = MediaInfo(
        path=Path("movie.mkv"),
        title="Movie",
        year=2020,
        duration_ms=1_000,
    )

    instructions = OpenAIService._translation_instructions(
        media,
        source_language="en",
        target_language=TargetLanguage.parse("French"),
    )

    assert "Translate only cues_to_translate into natural French" in instructions
    assert "Target language: French (fr)" in instructions
