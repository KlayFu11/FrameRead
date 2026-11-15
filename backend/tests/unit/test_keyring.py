import uuid

import pytest

from frameread.security.crypto import KeyPurpose, KeyRing, root_key_check

ROOT = bytes(range(32))
INSTALLATION = uuid.UUID("00000000-0000-4000-8000-000000000001")


def test_derive_is_stable_and_32_bytes_per_purpose():
    ring = KeyRing(ROOT, INSTALLATION)
    keys = {p: ring.derive(p) for p in KeyPurpose}
    assert {len(k) for k in keys.values()} == {32}
    assert len(set(keys.values())) == 4
    assert KeyRing(ROOT, INSTALLATION).derive(KeyPurpose.CURSOR) == keys[KeyPurpose.CURSOR]


def test_different_installation_derives_different_keys():
    other = uuid.UUID("00000000-0000-4000-8000-000000000002")
    assert KeyRing(ROOT, INSTALLATION).derive(KeyPurpose.SHARE) != KeyRing(ROOT, other).derive(KeyPurpose.SHARE)


def test_derive_matches_rfc5869_hkdf_sha256():
    # 独立实现：RFC 5869 extract-then-expand，单块输出 32 字节
    import hashlib
    import hmac

    prk = hmac.new(INSTALLATION.bytes, ROOT, hashlib.sha256).digest()
    expected = hmac.new(prk, b"frameread/v1/encryption" + b"\x01", hashlib.sha256).digest()
    assert KeyRing(ROOT, INSTALLATION).derive(KeyPurpose.ENCRYPTION) == expected


def test_unknown_purpose_rejected():
    with pytest.raises(ValueError):
        KeyRing(ROOT, INSTALLATION).derive("frameread/v1/other")  # type: ignore[arg-type]


def test_root_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        KeyRing(b"short", INSTALLATION)


def test_root_key_check_is_hmac_of_fixed_label():
    import hashlib
    import hmac

    assert root_key_check(ROOT) == hmac.new(ROOT, b"frameread/key-check", hashlib.sha256).digest()
    assert root_key_check(ROOT) != root_key_check(bytes(32))
