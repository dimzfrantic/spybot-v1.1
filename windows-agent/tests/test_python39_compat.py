from pathlib import Path


def test_agent_features_avoids_python310_union_syntax():
    content = Path("/home/ubnt/spybot-v1.1/agent_features.py").read_text(encoding="utf-8")

    assert "| None" not in content
