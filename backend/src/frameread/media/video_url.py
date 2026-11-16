import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qs, unquote, urlsplit


class VideoURLInputError(ValueError):
    """输入 URL 的结构不满足受理契约。"""


class UnsupportedVideoURL(ValueError):
    """URL 主机或路径不在 S0 支持范围内。"""


@dataclass(frozen=True, slots=True)
class ParsedVideoURL:
    platform: str
    platform_video_id: str
    part_id: str | None
    url: str


_BILIBILI_HOSTS = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _contains_control_or_backslash(value: str) -> bool:
    decoded = unquote(value)
    return any(ord(character) < 0x20 or ord(character) == 0x7F or character == "\\" for character in decoded)


def _validate_parts(raw_url: str) -> tuple[SplitResult, str]:
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > 2048:
        raise VideoURLInputError("invalid video URL")
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F or character == "\\"
        for character in raw_url
    ):
        raise VideoURLInputError("invalid video URL")
    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise VideoURLInputError("invalid video URL") from exc
    if parts.scheme.lower() != "https":
        raise VideoURLInputError("video URL must use HTTPS")
    if parts.username is not None or parts.password is not None:
        raise VideoURLInputError("video URL must not include userinfo")
    try:
        port = parts.port
    except ValueError as exc:
        raise VideoURLInputError("invalid video URL port") from exc
    if port not in (None, 443):
        raise VideoURLInputError("video URL must use the default HTTPS port")
    host = (parts.hostname or "").lower()
    if not host:
        raise VideoURLInputError("video URL host is required")
    return parts, host


def _single_query(query: str, key: str) -> str | None:
    values = parse_qs(query, keep_blank_values=True).get(key)
    if not values:
        return None
    value = values[-1].strip()
    return value or None


def _bilibili(parts: SplitResult, host: str) -> ParsedVideoURL:
    segments = parts.path.split("/")
    if len(segments) == 4 and segments[-1] == "":
        segments = segments[:-1]
    if len(segments) != 3 or segments[0] != "" or segments[1].lower() != "video":
        raise UnsupportedVideoURL("unsupported bilibili path")
    value = segments[2]
    if not value or _contains_control_or_backslash(value):
        raise VideoURLInputError("invalid bilibili video id")
    if not _SAFE_ID.fullmatch(value):
        raise UnsupportedVideoURL("unsupported bilibili video id")
    if value.lower().startswith("av"):
        if len(value) == 2:
            raise UnsupportedVideoURL("unsupported bilibili video id")
        platform_id = f"av{value[2:]}"
    elif value.lower().startswith("bv"):
        if len(value) == 2:
            raise UnsupportedVideoURL("unsupported bilibili video id")
        platform_id = f"BV{value[2:]}"
    else:
        raise UnsupportedVideoURL("unsupported bilibili video id")
    part = _single_query(parts.query, "p") or "1"
    if not part.isdecimal() or int(part) < 1:
        raise VideoURLInputError("invalid bilibili part")
    part = str(int(part))
    return ParsedVideoURL("bilibili", platform_id, part, f"https://www.bilibili.com/video/{platform_id}?p={part}")


def _safe_video_id(value: str | None) -> str | None:
    if value is None or not value:
        return None
    if _contains_control_or_backslash(value):
        raise VideoURLInputError("invalid video id")
    return value if _SAFE_ID.fullmatch(value) else None


def _youtube(parts: SplitResult, host: str) -> ParsedVideoURL:
    path = parts.path
    video_id: str | None = None
    if host == "youtu.be":
        segments = path.split("/")
        if len(segments) == 3 and segments[-1] == "":
            segments = segments[:-1]
        if len(segments) == 2 and segments[0] == "":
            video_id = segments[1]
    elif path in {"/watch", "/watch/"}:
        video_id = _single_query(parts.query, "v")
    elif path.startswith("/shorts/"):
        segments = path.split("/")
        if len(segments) == 4 and segments[-1] == "":
            segments = segments[:-1]
        if len(segments) == 3 and segments[0] == "" and segments[1] == "shorts":
            video_id = segments[2]
    video_id = _safe_video_id(video_id)
    if not video_id:
        raise UnsupportedVideoURL("unsupported youtube path")
    return ParsedVideoURL("youtube", video_id, None, f"https://www.youtube.com/watch?v={video_id}")


def parse_video_url(raw_url: str) -> ParsedVideoURL:
    """Parse and normalize an S0-supported URL without network or filesystem I/O."""
    parts, host = _validate_parts(raw_url)
    if host in _BILIBILI_HOSTS:
        return _bilibili(parts, host)
    if host == "b23.tv":
        segments = parts.path.split("/")
        if len(segments) == 3 and segments[-1] == "":
            segments = segments[:-1]
        if len(segments) != 2 or segments[0] != "" or not segments[1]:
            raise UnsupportedVideoURL("unsupported b23.tv path")
        code = segments[1]
        if _contains_control_or_backslash(code):
            raise VideoURLInputError("invalid b23.tv code")
        if not _SAFE_ID.fullmatch(code):
            raise UnsupportedVideoURL("unsupported b23.tv path")
        return ParsedVideoURL("b23", code, None, f"https://b23.tv/{code}")
    if host in _YOUTUBE_HOSTS or host == "youtu.be":
        return _youtube(parts, host)
    raise UnsupportedVideoURL("unsupported video host")
