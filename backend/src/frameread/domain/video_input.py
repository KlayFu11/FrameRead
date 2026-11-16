import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from frameread.media.video_url import parse_video_url

_DIGEST_FIELDS = (
    "url",
    "platform",
    "platform_video_id",
    "part_id",
    "mode",
    "depth",
    "focus",
    "provider_config_id",
    "asr_config_id",
    "intent",
)


def normalize_video_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical, JSON-compatible identity payload used by M03."""
    parsed = parse_video_url(value["url"])
    mode = value.get("mode", "complete")
    depth = value.get("depth", "standard")
    intent = value.get("intent", "new")
    focus = value.get("focus")
    if focus is not None:
        focus = str(focus).strip()
    provider = value.get("provider_config_id")
    asr = value.get("asr_config_id")
    normalized = {
        "url": parsed.url,
        "platform": parsed.platform,
        "platform_video_id": parsed.platform_video_id,
        "part_id": parsed.part_id,
        "mode": mode,
        "depth": depth,
        "focus": focus,
        "provider_config_id": provider,
        "asr_config_id": asr,
        "intent": intent,
        "config_resolution": "unresolved",
    }
    return normalized


def request_digest(value: Mapping[str, Any]) -> str:
    """Hash canonical identity fields with deterministic NFC JSON encoding."""
    payload = {key: value[key] for key in _DIGEST_FIELDS if key in value}
    for key in ("provider_config_id", "asr_config_id"):
        if payload.get(key) is None:
            payload[key] = "$default"

    def normalize(item: Any) -> Any:
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, Mapping):
            return {str(key): normalize(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [normalize(element) for element in item]
        return item

    encoded = json.dumps(normalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
