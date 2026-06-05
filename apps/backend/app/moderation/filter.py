import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

LEET_MAP = str.maketrans({
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
})

WORDLIST_PATH = os.path.join(os.path.dirname(__file__), "wordlist.json")


@dataclass
class FilterResult:
    censored_message: str
    matched_terms: list[str]
    had_match: bool


def _load_wordlist(path: str | None = None) -> list[str]:
    target = path or WORDLIST_PATH
    with open(target, encoding="utf-8") as handle:
        data = json.load(handle)
    terms = data.get("blocked_terms", [])
    return [str(term).strip().lower() for term in terms if str(term).strip()]


@lru_cache(maxsize=4)
def _cached_terms(path: str) -> tuple[str, ...]:
    return tuple(_load_wordlist(path))


def reload_wordlist() -> None:
    _cached_terms.cache_clear()


def normalize_token(token: str) -> str:
    lowered = token.lower().translate(LEET_MAP)
    lowered = re.sub(r"[^a-z0-9]+", "", lowered)
    lowered = re.sub(r"(.)\1{2,}", r"\1\1", lowered)
    return lowered


def normalize_message(message: str) -> str:
    return normalize_token(message.replace(" ", ""))


def _asterisk_replacement(original: str) -> str:
    return "*" * len(original)


def _iter_candidate_spans(message: str) -> Iterable[tuple[int, int, str]]:
    for match in re.finditer(r"\S+", message):
        yield match.start(), match.end(), match.group(0)


def _match_term_in_token(token: str, term: str) -> bool:
    normalized_token = normalize_token(token)
    normalized_term = normalize_token(term)
    if not normalized_token or not normalized_term:
        return False
    if normalized_token == normalized_term:
        return True
    if len(normalized_term) >= 4 and normalized_term in normalized_token:
        return True
    return False


def _match_spaced_term(message: str, term: str) -> list[tuple[int, int]]:
    normalized_term = normalize_token(term)
    if len(normalized_term) < 3:
        return []

    pattern = r"\b" + r"[\W_]*".join(re.escape(char) for char in normalized_term) + r"\b"
    spans: list[tuple[int, int]] = []
    for match in re.finditer(pattern, message, flags=re.IGNORECASE):
        spans.append((match.start(), match.end()))
    return spans


def filter_message(message: str, wordlist_path: str | None = None) -> FilterResult:
    path = wordlist_path or WORDLIST_PATH
    blocked_terms = _cached_terms(path)
    matched_terms: list[str] = []
    replacements: list[tuple[int, int, str]] = []

    for start, end, token in _iter_candidate_spans(message):
        for term in blocked_terms:
            if _match_term_in_token(token, term):
                matched_terms.append(term)
                replacements.append((start, end, _asterisk_replacement(token)))
                break

    for term in blocked_terms:
        for start, end in _match_spaced_term(message, term):
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _ in replacements):
                continue
            span_text = message[start:end]
            matched_terms.append(term)
            replacements.append((start, end, _asterisk_replacement(span_text)))

    if not replacements:
        compact = normalize_message(message)
        for term in blocked_terms:
            normalized_term = normalize_token(term)
            if normalized_term and normalized_term in compact:
                matched_terms.append(term)
                replacements.append((0, len(message), _asterisk_replacement(message)))
                break

    if not replacements:
        return FilterResult(censored_message=message, matched_terms=[], had_match=False)

    unique_terms = sorted(set(matched_terms))
    censored = message
    for start, end, masked in sorted(replacements, key=lambda item: item[0], reverse=True):
        censored = censored[:start] + masked + censored[end:]

    return FilterResult(
        censored_message=censored,
        matched_terms=unique_terms,
        had_match=True,
    )
