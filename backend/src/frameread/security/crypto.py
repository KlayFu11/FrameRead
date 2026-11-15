import hashlib
import hmac
import uuid
from enum import StrEnum

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROOT_KEY_BYTES = 32
SUBKEY_BYTES = 32
_KEY_CHECK_LABEL = b"frameread/key-check"


class KeyPurpose(StrEnum):
    ENCRYPTION = "frameread/v1/encryption"
    SESSION_CSRF = "frameread/v1/session-csrf"
    CURSOR = "frameread/v1/cursor"
    SHARE = "frameread/v1/share"


class KeyRing:
    """根密钥经 HKDF-SHA256 派生用途子密钥，salt 绑定 installation_id。"""

    def __init__(self, root_key: bytes, installation_id: uuid.UUID) -> None:
        if len(root_key) != ROOT_KEY_BYTES:
            raise ValueError("根密钥必须为 32 字节")
        self._root_key = root_key
        self._salt = installation_id.bytes

    def derive(self, purpose: KeyPurpose) -> bytes:
        purpose = KeyPurpose(purpose)
        return HKDF(
            algorithm=hashes.SHA256(),
            length=SUBKEY_BYTES,
            salt=self._salt,
            info=purpose.value.encode(),
        ).derive(self._root_key)


def root_key_check(root_key: bytes) -> bytes:
    return hmac.new(root_key, _KEY_CHECK_LABEL, hashlib.sha256).digest()
