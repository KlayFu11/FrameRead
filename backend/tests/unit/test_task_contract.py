from frameread.api.admin_app import build_app


def test_video_admission_openapi_requires_idempotency_key() -> None:
    operation = build_app().openapi()["paths"]["/api/v1/admin/video-tasks"]["post"]
    header = next(item for item in operation["parameters"] if item["name"] == "idempotency-key")
    assert header["in"] == "header"
    assert header["required"] is True
    assert header["schema"]["type"] == "string"
