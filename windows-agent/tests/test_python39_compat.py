from pathlib import Path


WINDOWS_AGENT_DIR = Path(__file__).resolve().parents[1]


def test_agent_features_avoids_python310_union_syntax():
    content = (WINDOWS_AGENT_DIR / "agent_features.py").read_text(encoding="utf-8")

    assert "| None" not in content
