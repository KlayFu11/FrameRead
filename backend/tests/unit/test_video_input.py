import hashlib
import json

import pytest

from frameread.domain.video_input import normalize_video_input, request_digest
from frameread.media.video_url import UnsupportedVideoURL, VideoURLInputError, parse_video_url


@pytest.mark.parametrize(
    ("url", "canonical", "part"),
    [
        ("https://www.bilibili.com/video/BV1abc?p=2&utm_source=x", "https://www.bilibili.com/video/BV1abc?p=2", "2"),
        ("https://www.bilibili.com/video/BV1abc?p=01", "https://www.bilibili.com/video/BV1abc?p=1", "1"),
        ("https://bilibili.com/video/BV1abc", "https://www.bilibili.com/video/BV1abc?p=1", "1"),
        (
            "https://www.youtube.com/watch?v=abc123&list=PL1&utm_source=x",
            "https://www.youtube.com/watch?v=abc123",
            None,
        ),
        ("https://youtu.be/abc123?list=PL1", "https://www.youtube.com/watch?v=abc123", None),
        ("https://m.youtube.com/shorts/abc123?feature=share", "https://www.youtube.com/watch?v=abc123", None),
        ("https://b23.tv/AbC9?share_source=copy", "https://b23.tv/AbC9", None),
    ],
)
def test_parse_video_url_normalizes_supported_variants(url, canonical, part):
    parsed = parse_video_url(url)
    assert parsed.url == canonical
    assert parsed.part_id == part


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=x",
        "https://user:pass@www.youtube.com/watch?v=x",
        "https://www.youtube.com:444/watch?v=x",
        "https://www.bilibili.com/video/BV1abc?p=%C2%B2",
    ],
)
def test_parse_video_url_rejects_unsafe_shape(url):
    with pytest.raises(VideoURLInputError):
        parse_video_url(url)


@pytest.mark.parametrize(
    "url",
    ["https://vimeo.com/123", "https://www.youtube.com/embed/x", "https://b23.tv/"],
)
def test_parse_video_url_rejects_unsupported_host_or_path(url):
    with pytest.raises(UnsupportedVideoURL):
        parse_video_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/av/BV1abc",
        "https://www.bilibili.com/video//BV1abc",
        "https://www.bilibili.com/video/BV1abc//",
        "https://youtu.be//abc123",
        "https://www.youtube.com/shorts//abc123",
    ],
)
def test_parse_video_url_rejects_empty_or_invented_path_segments(url):
    with pytest.raises(UnsupportedVideoURL):
        parse_video_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=ab%2Fcd",
        "https://www.youtube.com/watch?v=ab%5Ccd",
        "https://b23.tv/ab%5Ccd",
    ],
)
def test_parse_video_url_rejects_encoded_dangerous_ids(url):
    expected = VideoURLInputError if "%5C" in url else UnsupportedVideoURL
    with pytest.raises(expected):
        parse_video_url(url)


def test_normalize_and_digest_ignore_tracking_and_trim_focus():
    first = normalize_video_input(
        {"url": "https://youtu.be/x?utm_source=one", "focus": "  a\u0301 ", "mode": "complete", "depth": "standard"}
    )
    second = normalize_video_input(
        {"url": "https://www.youtube.com/watch?v=x&list=all", "focus": "á", "mode": "complete", "depth": "standard"}
    )
    assert first["url"] == second["url"]
    assert first["focus"] != second["focus"]
    assert first["config_resolution"] == "unresolved"
    assert request_digest(first) == request_digest(second)


def test_bilibili_default_part_and_explicit_one_share_identity():
    implicit = normalize_video_input({"url": "https://www.bilibili.com/video/BV1abc"})
    explicit = normalize_video_input({"url": "https://bilibili.com/video/BV1abc?p=01"})
    assert implicit["part_id"] == explicit["part_id"] == "1"
    assert request_digest(implicit) == request_digest(explicit)


def test_digest_uses_default_config_sentinels_and_omits_resolution():
    normalized = normalize_video_input({"url": "https://youtu.be/x"})
    normalized["session_id"] = "must-not-affect-identity"
    expected_payload = dict(normalized)
    expected_payload.pop("config_resolution")
    expected_payload.pop("session_id")
    expected_payload["provider_config_id"] = "$default"
    expected_payload["asr_config_id"] = "$default"

    expected_json = json.dumps(expected_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert request_digest(normalized) == expected


def test_digest_matches_independent_canonical_fixture():
    canonical = {
        "url": "https://www.youtube.com/watch?v=abc123",
        "platform": "youtube",
        "platform_video_id": "abc123",
        "part_id": None,
        "mode": "complete",
        "depth": "standard",
        "focus": "重点",
        "provider_config_id": "$default",
        "asr_config_id": "$default",
        "intent": "new",
    }
    assert request_digest(canonical) == "2e820533b85543540df0918da81ea5771e7c4af170c2f7cfae12f2a68cae177c"
