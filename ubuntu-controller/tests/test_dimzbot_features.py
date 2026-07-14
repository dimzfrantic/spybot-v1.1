import importlib.util
import sys
import types
from pathlib import Path


fake_wakeonlan = types.ModuleType("wakeonlan")
fake_wakeonlan.send_magic_packet = lambda *args, **kwargs: None
sys.modules.setdefault("wakeonlan", fake_wakeonlan)

SPEC = importlib.util.spec_from_file_location(
    "masterwol_module",
    Path(__file__).resolve().parents[1] / "masterwol.py",
)
masterwol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(masterwol)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHTTPError(Exception):
    def __init__(self, payload):
        super().__init__("boom")
        self.response = FakeResponse(payload)


def test_build_explorer_callback_uses_short_token_for_long_path():
    long_path = "C:/Users/Administrator/Documents/FolderSangatPanjang/SubFolderPanjang/Lagi/DanLagi/Final"

    callback_data = masterwol.build_explorer_callback("dir", long_path)

    assert len(callback_data.encode("utf-8")) <= 64
    token = callback_data.split("|", 2)[2]
    assert masterwol.resolve_explorer_path(token) == long_path


def test_get_parent_windows_path_uses_windows_semantics():
    assert masterwol.get_parent_windows_path("C:/Users/Public/Documents") == "C:/Users/Public"
    assert masterwol.get_parent_windows_path("C:/") == "C:/"


def test_confirmation_menu_contains_yes_and_no_actions():
    menu = masterwol.get_confirmation_menu("restart_pcutama", "Restart PC utama?")

    rows = menu["inline_keyboard"]
    all_callbacks = [btn["callback_data"] for row in rows for btn in row]
    assert "confirm|restart_pcutama|yes" in all_callbacks
    assert "confirm|restart_pcutama|no" in all_callbacks


def test_get_explorer_menu_keeps_file_buttons_visible_when_many_folders_exist():
    items = [{"name": f"Folder{i}", "path": f"C:/Folder{i}", "type": "dir"} for i in range(12)]
    items += [
        {"name": "laporan.pdf", "path": "C:/laporan.pdf", "type": "file", "size": 123},
        {"name": "data.xlsx", "path": "C:/data.xlsx", "type": "file", "size": 456},
    ]

    menu = masterwol.get_explorer_menu(items, "C:/")
    labels = [btn["text"] for row in menu["inline_keyboard"] for btn in row]

    assert any("laporan.pdf" in label for label in labels)
    assert any("data.xlsx" in label for label in labels)


def test_format_explorer_text_only_shows_path_not_item_listing():
    data = {
        "path": "C:/Users/Public",
        "items": [
            {"name": "FolderA", "type": "dir"},
            {"name": "rahasia.txt", "type": "file", "size": 10},
        ],
    }

    text = masterwol.format_explorer_text(data)

    assert "C:/Users/Public" in text
    assert "FolderA" not in text
    assert "rahasia.txt" not in text


def test_send_explorer_listing_calls_agent_once(monkeypatch):
    calls = []

    def fake_call(method, path, params=None):
        calls.append((method, path, params))
        return {
            "data": {
                "path": "C:/",
                "items": [{"name": "Docs", "path": "C:/Docs", "type": "dir"}],
            }
        }

    sent = {}

    monkeypatch.setattr(masterwol, "call_pc_agent_json", fake_call)
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.update({"text": text, "reply_markup": reply_markup, "chat_id": chat_id}))

    masterwol.send_explorer_listing("C:/")

    assert len(calls) == 1
    assert "Docs" not in sent["text"]
    assert sent["reply_markup"] is not None


def test_send_pc_camera_uses_configured_camera_index(monkeypatch):
    calls = []

    monkeypatch.setattr(masterwol, "PC_CAMERA_INDEX", "1")
    monkeypatch.setattr(masterwol, "download_agent_file", lambda path, filename=None: calls.append((path, filename)) or "/tmp/camera.jpg")
    monkeypatch.setattr(masterwol, "send_photo_file", lambda path, caption, chat_id=None: None)

    masterwol.send_pc_camera()

    assert calls[0][0] == "/camera?index=1"


def test_format_agent_error_prefers_response_message():
    error = FakeHTTPError({"message": "Akses folder ditolak"})

    message = masterwol.format_agent_error(error, "Gagal membuka folder")

    assert "Akses folder ditolak" in message


def test_get_explorer_menu_adds_next_page_when_items_exceed_first_page():
    items = [{"name": f"Folder{i}", "path": f"C:/Folder{i}", "type": "dir"} for i in range(20)]

    menu = masterwol.get_explorer_menu(items, "C:/")
    labels = [btn["text"] for row in menu["inline_keyboard"] for btn in row]

    assert any("Berikutnya" in label for label in labels)


def test_get_explorer_menu_can_render_second_page_items():
    items = [{"name": f"Folder{i}", "path": f"C:/Folder{i}", "type": "dir"} for i in range(20)]

    menu = masterwol.get_explorer_menu(items, "C:/", page=1)
    labels = [btn["text"] for row in menu["inline_keyboard"] for btn in row]

    assert any("Folder12" in label for label in labels)
    assert any("Sebelumnya" in label for label in labels)
