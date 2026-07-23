from app.utils.session import create_session_token, decode_session_token


def test_create_and_decode_session_token_round_trip():
    token = create_session_token(42)
    assert decode_session_token(token) == 42


def test_decode_session_token_rejects_tampered_token():
    token = create_session_token(7)
    header, payload, signature = token.split(".")
    # Flip a high-entropy signature character. Changing only the final base64
    # character is unreliable: unused padding bits mean several alphabet chars
    # (e.g. Y/Z/a/b) decode to the same signature bytes.
    sig_chars = list(signature)
    mid = len(sig_chars) // 2
    sig_chars[mid] = "A" if sig_chars[mid] != "A" else "B"
    tampered = f"{header}.{payload}.{''.join(sig_chars)}"
    assert tampered != token
    assert decode_session_token(tampered) is None


def test_decode_session_token_rejects_raw_user_id():
    assert decode_session_token("123") is None
