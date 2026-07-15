import importlib.util
import sys
import types
from pathlib import Path


fake_wakeonlan = types.ModuleType("wakeonlan")
fake_wakeonlan.send_magic_packet = lambda *args, **kwargs: None
sys.modules.setdefault("wakeonlan", fake_wakeonlan)

SPEC = importlib.util.spec_from_file_location(
    "masterwol_dm_module",
    Path(__file__).resolve().parents[1] / "masterwol.py",
)
masterwol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(masterwol)


def target(owner_id="987654321", name="PC User A", mac="AA:BB:CC:DD:EE:FF", broadcast="10.147.20.255", agent_url="http://pc-user-a:8787", token="agent-user-a", allow_server_restart=False):
    return {
        "owner_id": owner_id,
        "name": name,
        "mac": mac,
        "broadcast": broadcast,
        "ip": "",
        "agent_base_url": agent_url,
        "agent_token": token,
        "camera_index": "",
        "allow_server_restart": allow_server_restart,
    }


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


def test_send_msg_can_target_dm_chat_without_using_group(monkeypatch):
    posted = {}

    def fake_post(url, data=None, timeout=None, **kwargs):
        posted.update(data or {})
        return FakeResponse()

    monkeypatch.setattr(masterwol, "GROUP_CHAT_ID", "-100999")
    monkeypatch.setattr(masterwol.SESSION, "post", fake_post)

    masterwol.send_msg("halo", chat_id="111111111")

    assert posted["chat_id"] == "111111111"


def test_send_msg_defaults_to_admin_dm_when_available(monkeypatch):
    posted = {}

    def fake_post(url, data=None, timeout=None, **kwargs):
        posted.update(data or {})
        return FakeResponse()

    monkeypatch.setattr(masterwol, "GROUP_CHAT_ID", "-100999")
    monkeypatch.setattr(masterwol, "ADMIN_TELEGRAM_ID", "111111111")
    monkeypatch.setattr(masterwol.SESSION, "post", fake_post)

    masterwol.send_msg("startup")

    assert posted["chat_id"] == "111111111"


def test_private_admin_menu_replies_to_private_chat(monkeypatch):
    sent = []

    monkeypatch.setattr(masterwol, "ADMIN_TELEGRAM_ID", "111111111")
    monkeypatch.setattr(masterwol, "is_pc_utama_online", lambda: True)
    monkeypatch.setattr(masterwol, "get_ubuntu_status", lambda: "STATUS UBUNTU")
    monkeypatch.setattr(masterwol, "cek_pc_utama", lambda: "STATUS PC")
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, chat_id)))

    handled = masterwol.handle_command(
        "/menu",
        chat_id="111111111",
        user_id="111111111",
        chat_type="private",
    )

    assert handled is True
    assert sent
    assert sent[0][1] == "111111111"


def test_private_non_admin_cannot_open_full_menu(monkeypatch):
    sent = []

    monkeypatch.setattr(masterwol, "ADMIN_TELEGRAM_ID", "111111111")
    monkeypatch.setattr(masterwol, "USER_A_TELEGRAM_ID", "")
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, chat_id)))

    handled = masterwol.handle_command(
        "/menu",
        chat_id="999",
        user_id="999",
        chat_type="private",
    )

    assert handled is True
    assert sent
    assert sent[0][1] == "999"
    assert "tidak memiliki akses" in sent[0][0].lower()


def test_user_target_gets_full_menu_for_own_pc(monkeypatch):
    sent = []

    monkeypatch.setattr(masterwol, "TARGET_CONFIGS", [target(name="PC Randy")])
    monkeypatch.setattr(masterwol, "is_pc_online", lambda selected_target=None: True)
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, reply_markup, chat_id)))

    handled = masterwol.handle_command(
        "/menu",
        chat_id="987654321",
        user_id="987654321",
        chat_type="private",
    )

    assert handled is True
    assert sent[0][2] == "987654321"
    labels = [button["text"] for row in sent[0][1]["inline_keyboard"] for button in row]
    callbacks = [button["callback_data"] for row in sent[0][1]["inline_keyboard"] for button in row]
    assert any("Status PC Randy" in label for label in labels)
    assert any("Camera" in label for label in labels)
    assert any("Screenshot" in label for label in labels)
    assert any("Explorer" in label for label in labels)
    assert "menu|restart_server" not in callbacks


def test_user_start_opens_full_menu_for_own_pc(monkeypatch):
    sent = []

    monkeypatch.setattr(masterwol, "TARGET_CONFIGS", [target(name="PC Randy")])
    monkeypatch.setattr(masterwol, "is_pc_online", lambda selected_target=None: False)
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, reply_markup, chat_id)))

    handled = masterwol.handle_command(
        "/start",
        chat_id="987654321",
        user_id="987654321",
        chat_type="private",
    )

    assert handled is True
    assert sent[0][2] == "987654321"
    assert sent[0][1]["inline_keyboard"][0][0]["callback_data"] == "menu|nyalakanpc"
    assert "PC Randy" in sent[0][1]["inline_keyboard"][0][0]["text"]


def test_limited_user_wake_command_uses_user_a_mac(monkeypatch):
    sent = []
    packets = []
    sleeps = []

    monkeypatch.setattr(masterwol, "TARGET_CONFIGS", [target()])
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, chat_id)))
    monkeypatch.setattr(masterwol, "send_wol_packet", lambda mac, broadcast=None: packets.append((mac, broadcast)))
    monkeypatch.setattr(masterwol.time, "sleep", lambda seconds: sleeps.append(seconds))

    handled = masterwol.handle_command(
        "/nyalakanpc",
        chat_id="987654321",
        user_id="987654321",
        chat_type="private",
    )

    assert handled is True
    assert packets == [("AA:BB:CC:DD:EE:FF", "10.147.20.255")] * 3
    assert sent[-1][1] == "987654321"
    assert "PC User A" in sent[-1][0]


def test_user_camera_targets_own_pc(monkeypatch):
    sent = []
    called = []

    monkeypatch.setattr(masterwol, "TARGET_CONFIGS", [target()])
    monkeypatch.setattr(masterwol, "send_pc_camera", lambda chat_id=None, target=None: called.append(target))
    monkeypatch.setattr(masterwol, "send_msg", lambda text, reply_markup=None, chat_id=None: sent.append((text, chat_id)))

    handled = masterwol.handle_command(
        "/camera_pcutama",
        chat_id="987654321",
        user_id="987654321",
        chat_type="private",
    )

    assert handled is True
    assert called and called[0]["name"] == "PC User A"


def test_agent_call_uses_selected_user_target_credentials(monkeypatch):
    requests_seen = []

    class Response:
        def raise_for_status(self):
            return None

    def fake_request(**kwargs):
        requests_seen.append(kwargs)
        return Response()

    user_target = target(agent_url="http://pc-randy:8787", token="token-randy")
    monkeypatch.setattr(masterwol.SESSION, "request", fake_request)

    masterwol.call_pc_agent("GET", "/status", target=user_target)

    assert requests_seen[0]["url"] == "http://pc-randy:8787/status"
    assert requests_seen[0]["headers"] == {"X-Agent-Token": "token-randy"}
