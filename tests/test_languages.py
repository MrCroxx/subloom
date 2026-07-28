import pytest

from subloom.languages import TargetLanguage, languages_match


def test_target_language_accepts_bcp47_tags_and_english_names() -> None:
    french = TargetLanguage.parse("fr")
    portuguese = TargetLanguage.parse("Brazilian Portuguese")

    assert french.tag == "fr"
    assert french.display_name == "French"
    assert portuguese.tag == "pt-BR"
    assert portuguese.base_code == "pt"


def test_target_language_normalizes_iso_639_2_codes() -> None:
    language = TargetLanguage.parse("zho")

    assert language.tag == "zh"
    assert language.base_code == "zh"


def test_target_language_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="unknown"):
        TargetLanguage.parse("not a real language")


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("fra", "fr", True),
        ("eng", "en-US", True),
        ("pt-BR", "pt-PT", False),
        ("zh-Hans", "zh-Hant", False),
        ("ja", "fr", False),
        (None, "fr", False),
    ],
)
def test_languages_match_compatible_language_metadata(
    left: str | None,
    right: str | None,
    expected: bool,
) -> None:
    assert languages_match(left, right) is expected
