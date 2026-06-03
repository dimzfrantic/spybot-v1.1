import importlib.util
import sys
import types


fake_wakeonlan = types.ModuleType("wakeonlan")
fake_wakeonlan.send_magic_packet = lambda *args, **kwargs: None
sys.modules.setdefault("wakeonlan", fake_wakeonlan)

SPEC = importlib.util.spec_from_file_location(
    "masterwol_module",
    "/home/ubnt/masterWOL/masterwol.py",
)
masterwol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(masterwol)


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
