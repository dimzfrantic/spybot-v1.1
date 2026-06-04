from pathlib import Path


WINDOWS_AGENT_DIR = Path(__file__).resolve().parents[1]


def test_requirements_include_requests_for_boot_notify():
    content = (WINDOWS_AGENT_DIR / "requirements.txt").read_text(encoding="utf-8")

    assert "requests" in {line.strip() for line in content.splitlines() if line.strip()}
