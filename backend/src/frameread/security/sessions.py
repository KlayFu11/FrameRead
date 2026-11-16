import hashlib
import hmac
from urllib.parse import urlsplit


def credential_generation(secret_bytes: bytes) -> str:
    return hashlib.sha256(secret_bytes).hexdigest()[:16]


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def csrf_token(key: bytes, token: str) -> str:
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def source_hash(key: bytes, source: str) -> str:
    return hmac.new(key, b"login-source:" + source.encode(), hashlib.sha256).hexdigest()


def origin_allowed(origin: str | None, origins: list[str]) -> bool:
    return origin is not None and origin in origins


def host_allowed(host: str, origins: list[str]) -> bool:
    return any(host == urlsplit(origin).netloc for origin in origins)
