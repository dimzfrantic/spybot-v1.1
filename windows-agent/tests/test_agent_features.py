import app as app_module


class DummyResponse:
    def __init__(self, data: bytes, mimetype: str = "application/octet-stream"):
        self.status_code = 200
        self.data = data
        self.mimetype = mimetype
        self.headers = {}


class DummyClient:
    def __init__(self):
        self.info_payload = None

    def get_info(self):
        return self.info_payload


def test_info_lists_extended_capabilities():
    payload = {
        "ok": True,
        "supports": [
            "health",
            "info",
            "status",
            "restart",
            "shutdown",
            "screenshot",
            "camera",
            "explorer",
            "download",
        ],
    }

    assert payload["ok"] is True
    assert "screenshot" in payload["supports"]
    assert "camera" in payload["supports"]
    assert "explorer" in payload["supports"]
    assert "download" in payload["supports"]


def test_screenshot_contract(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.jpg"
    screenshot_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        app_module,
        "capture_screenshot",
        lambda: {
            "ok": True,
            "path": screenshot_path,
            "filename": "screen.jpg",
            "mimetype": "image/jpeg",
        },
    )

    monkeypatch.setattr(
        app_module,
        "send_file",
        lambda path, mimetype, as_attachment, download_name: DummyResponse(path.read_bytes(), mimetype),
    )
    monkeypatch.setattr(app_module, "AGENT_NAME", "test-agent")

    with app_module.app.test_request_context("/screenshot"):
        response = app_module.screenshot.__wrapped__()

    assert response.status_code == 200
    assert response.data == b"fake-image"
    assert response.mimetype == "image/jpeg"
    assert response.headers["X-Agent-Host"] == "test-agent"


def test_camera_contract(monkeypatch, tmp_path):
    camera_path = tmp_path / "camera.jpg"
    camera_path.write_bytes(b"fake-camera")

    monkeypatch.setattr(
        app_module,
        "capture_camera_image",
        lambda: {
            "ok": True,
            "path": camera_path,
            "filename": "camera.jpg",
            "mimetype": "image/jpeg",
        },
    )
    monkeypatch.setattr(
        app_module,
        "send_file",
        lambda path, mimetype, as_attachment, download_name: DummyResponse(path.read_bytes(), mimetype),
    )
    monkeypatch.setattr(app_module, "AGENT_NAME", "test-agent")

    with app_module.app.test_request_context("/camera"):
        response = app_module.camera.__wrapped__()

    assert response.status_code == 200
    assert response.data == b"fake-camera"
    assert response.mimetype == "image/jpeg"
    assert response.headers["X-Agent-Host"] == "test-agent"


def test_explorer_contract(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "list_directory",
        lambda target_path: {
            "ok": True,
            "path": str(target_path),
            "items": [
                {"name": "Docs", "type": "dir"},
                {"name": "notes.txt", "type": "file", "size": 12},
            ],
        },
    )
    monkeypatch.setattr(app_module, "AGENT_NAME", "test-agent")

    with app_module.app.test_request_context("/explorer?path=C:/Users"):
        response = app_module.explorer.__wrapped__()

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["host"] == "test-agent"
    assert payload["data"]["items"][0]["name"] == "Docs"
    assert payload["data"]["items"][1]["type"] == "file"


def test_download_contract(monkeypatch, tmp_path):
    file_path = tmp_path / "report.txt"
    file_path.write_text("halo", encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "prepare_download_file",
        lambda target_path: {
            "ok": True,
            "path": file_path,
            "filename": "report.txt",
            "mimetype": "text/plain",
        },
    )
    monkeypatch.setattr(
        app_module,
        "send_file",
        lambda path, mimetype, as_attachment, download_name: DummyResponse(path.read_bytes(), mimetype),
    )
    monkeypatch.setattr(app_module, "AGENT_NAME", "test-agent")

    with app_module.app.test_request_context("/download?path=C:/report.txt"):
        response = app_module.download.__wrapped__()

    assert response.status_code == 200
    assert response.data == b"halo"
    assert response.mimetype == "text/plain"
    assert response.headers["X-Agent-Host"] == "test-agent"


def test_download_requires_path(monkeypatch):
    monkeypatch.setattr(app_module, "AGENT_NAME", "test-agent")

    with app_module.app.test_request_context("/download"):
        response, status_code = app_module.handle_agent_feature_error(
            app_module.AgentFeatureError("missing_path", "Parameter path wajib diisi", 400)
        )

    payload = response.get_json()
    assert status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "missing_path"
