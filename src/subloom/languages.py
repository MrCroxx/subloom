from dataclasses import dataclass

from langcodes import Language, find
from langcodes.tag_parser import LanguageTagError


@dataclass(frozen=True, slots=True)
class TargetLanguage:
    tag: str
    display_name: str
    base_code: str

    @classmethod
    def parse(cls, value: str) -> "TargetLanguage":
        raw = value.strip()
        if not raw:
            raise ValueError("target language must not be empty")

        try:
            language = _parse_language(raw)
        except ValueError as error:
            raise ValueError(f"unknown target language: {value}") from error
        if not language.is_valid() or not language.language or language.language == "und":
            raise ValueError(f"unknown target language: {value}")

        return cls(
            tag=language.to_tag(),
            display_name=language.display_name("en"),
            base_code=language.language,
        )


def languages_match(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    try:
        left_language = _parse_language(left)
        right_language = _parse_language(right)
    except ValueError:
        return left.casefold() == right.casefold()

    if left_language.language != right_language.language:
        return False
    if (
        left_language.script
        and right_language.script
        and left_language.script != right_language.script
    ):
        return False
    return not (
        left_language.territory
        and right_language.territory
        and left_language.territory != right_language.territory
    )


def _parse_language(value: str) -> Language:
    try:
        return Language.get(value)
    except LanguageTagError:
        try:
            return find(value)
        except LookupError as error:
            raise ValueError(f"unknown language: {value}") from error
