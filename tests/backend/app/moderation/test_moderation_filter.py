import json
import os
import tempfile

from app.moderation.filter import filter_message, normalize_token, reload_wordlist


def test_normalize_token_strips_obfuscation():
    assert normalize_token("sh1t") == "shit"
    assert normalize_token("b4dword") == "badword"


def test_filter_replaces_blocked_word_with_asterisks():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump({"blocked_terms": ["badword"]}, handle)
        path = handle.name

    try:
        reload_wordlist()
        result = filter_message("hello badword there", wordlist_path=path)
        assert result.had_match is True
        assert result.censored_message == "hello ******* there"
        assert result.matched_terms == ["badword"]
    finally:
        os.unlink(path)
        reload_wordlist()


def test_filter_leaves_clean_message_unchanged():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump({"blocked_terms": ["badword"]}, handle)
        path = handle.name

    try:
        reload_wordlist()
        result = filter_message("hello trainer", wordlist_path=path)
        assert result.had_match is False
        assert result.censored_message == "hello trainer"
        assert result.matched_terms == []
    finally:
        os.unlink(path)
        reload_wordlist()
