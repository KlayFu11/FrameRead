import pytest

from frameread.security.sessions import credential_generation, csrf_token, host_allowed, origin_allowed, source_hash


def test_credential_generation_is_hash_of_exact_secret_bytes():
    assert credential_generation(b"abc") == "ba7816bf8f01cfea"
    assert credential_generation(b"abc\n") == "edeaaff3f1774ad2"


def test_csrf_and_source_are_deterministic_and_domain_separated():
    key = bytes(range(32))
    assert csrf_token(key, "127.0.0.1") == csrf_token(key, "127.0.0.1")
    assert source_hash(key, "127.0.0.1") == source_hash(key, "127.0.0.1")
    assert source_hash(key, "127.0.0.1") != source_hash(key, "127.0.0.2")
    assert csrf_token(key, "127.0.0.1") != source_hash(key, "127.0.0.1")
    assert csrf_token(b"key", "The quick brown fox jumps over the lazy dog") == (
        "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
    )


@pytest.mark.parametrize(
    "value,allowed",
    [
        ("http://localhost:8080", True),
        ("http://LOCALHOST:8080", False),
        ("http://localhost:8080/", False),
        ("https://localhost:8080", False),
        ("http://user@localhost:8080", False),
        ("http://127.0.0.1:8080", False),
        ("http://localhost", False),
        (None, False),
    ],
)
def test_origin_matches_exact_configured_string(value, allowed):
    assert origin_allowed(value, ["http://localhost:8080"]) is allowed


@pytest.mark.parametrize(
    "value,allowed",
    [
        ("localhost:8080", True),
        ("LOCALHOST:8080", False),
        ("localhost", False),
        ("localhost:8080/", False),
        ("user@localhost:8080", False),
        ("127.0.0.1:8080", False),
    ],
)
def test_host_matches_exact_configured_authority(value, allowed):
    assert host_allowed(value, ["http://localhost:8080"]) is allowed
