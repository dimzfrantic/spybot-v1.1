from pathlib import Path

import pytest

from agent_features import AgentFeatureError, list_directory, prepare_download_file


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "A" / "B" / "C"
    nested.mkdir(parents=True)
    file_path = nested / "sample.txt"
    file_path.write_text("hello", encoding="utf-8")
    monkeypatch.chdir(root)
    return root, nested, file_path


def test_list_directory_supports_relative_parent_navigation(workspace):
    root, nested, file_path = workspace

    payload = list_directory(str(Path("A") / "B" / "C" / ".." / ".."))

    assert payload["ok"] is True
    assert payload["path"].endswith(str(Path("A")))


def test_prepare_download_file_supports_parent_relative_path(workspace):
    root, nested, file_path = workspace

    payload = prepare_download_file(str(Path("A") / "B" / "C" / "sample.txt"))

    assert payload["ok"] is True
    assert payload["filename"] == "sample.txt"


def test_list_directory_returns_clear_error_for_missing_path(workspace):
    with pytest.raises(AgentFeatureError) as exc:
        list_directory("Z:/path/yang/tidak/ada")

    assert exc.value.error == "path_not_found"
