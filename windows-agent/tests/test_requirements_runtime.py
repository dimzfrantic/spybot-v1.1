from pathlib import Path


def test_requirements_include_requests_for_boot_notify():
    content = Path("/home/ubnt/spybot-v1.1/requirements.txt").read_text(encoding="utf-8")

    assert "requests" in {line.strip() for line in content.splitlines() if line.strip()}
