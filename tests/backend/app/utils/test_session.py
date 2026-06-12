from app.utils.session import create_session_token, decode_session_token


def test_create_and_decode_session_token_round_trip():
    token = create_session_token(42)
    assert decode_session_token(token) == 42


def test_decode_session_token_rejects_tampered_token():
    token = create_session_token(7)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert decode_session_token(tampered) is None


def test_decode_session_token_rejects_raw_user_id():
    assert decode_session_token("123") is None
