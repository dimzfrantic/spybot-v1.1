import importlib.util
import os
import sys
import types
from pathlib import Path


fake_wakeonlan = types.ModuleType("wakeonlan")
fake_wakeonlan.send_magic_packet = lambda *args, **kwargs: None
sys.modules.setdefault("wakeonlan", fake_wakeonlan)

MODULE_PATH = Path("/home/ubnt/spybot-publish/ubuntu-controller/masterwol.py")


def load_masterwol(module_name):
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_masterwol_reads_token_and_agent_config_from_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TOKEN=token-dari-env\n"
        "GROUP_CHAT_ID=-100123\n"
        "TARGET_MAC=11:22:33:44:55:66\n"
        "TARGET_PC_IP=10.1.2.3\n"
        "PC_AGENT_BASE_URL=http://10.1.2.3:8787\n"
        "PC_AGENT_TOKEN=rahasia-agent\n",
        encoding="utf-8",
    )

    for key in [
        "TOKEN",
        "GROUP_CHAT_ID",
        "TARGET_MAC",
        "TARGET_PC_IP",
        "PC_AGENT_BASE_URL",
        "PC_AGENT_TOKEN",
        "DIMZBOT_ENV_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DIMZBOT_ENV_FILE", str(env_path))

    masterwol = load_masterwol("masterwol_env_file_test")

    assert masterwol.TOKEN == "token-dari-env"
    assert masterwol.GROUP_CHAT_ID == "-100123"
    assert masterwol.TARGET_MAC == "11:22:33:44:55:66"
    assert masterwol.TARGET_PC_IP == "10.1.2.3"
    assert masterwol.PC_AGENT_BASE_URL == "http://10.1.2.3:8787"
    assert masterwol.PC_AGENT_TOKEN == "rahasia-agent"
    assert masterwol.API_BASE == "https://api.telegram.org/bottoken-dari-env"


def test_masterwol_prefers_process_env_over_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TOKEN=token-file\n"
        "GROUP_CHAT_ID=-100456\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DIMZBOT_ENV_FILE", str(env_path))
    monkeypatch.setenv("TOKEN", "token-process")
    monkeypatch.setenv("GROUP_CHAT_ID", "-100999")

    masterwol = load_masterwol("masterwol_env_override_test")

    assert masterwol.TOKEN == "token-process"
    assert masterwol.GROUP_CHAT_ID == "-100999"
