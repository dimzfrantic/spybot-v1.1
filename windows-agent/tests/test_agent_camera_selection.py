import sys
import types
from pathlib import Path

import pytest

import agent_features
from agent_features import AgentFeatureError, capture_camera_image


class FakeFrame:
    def __init__(self, std_value):
        self._std_value = std_value

    def std(self):
        return self._std_value


class FakeNumpyScalar:
    def __init__(self, value):
        self.value = value

    def __float__(self):
        return float(self.value)


class FakeCapture:
    def __init__(self, opened, frame=None):
        self._opened = opened
        self._frame = frame
        self.released = False

    def isOpened(self):
        return self._opened

    def read(self):
        if self._frame is None:
            return False, None
        return True, self._frame

    def release(self):
        self.released = True


@pytest.fixture()
def artifact_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_features, "ARTIFACT_DIR", tmp_path)
    return tmp_path


def test_capture_camera_image_skips_blank_virtual_camera(monkeypatch, artifact_dir):
    captures = {
        0: FakeCapture(True, FakeFrame(0.0)),
        1: FakeCapture(True, FakeFrame(22.0)),
    }
    opened_indices = []
    saved = {}

    fake_cv2 = types.SimpleNamespace()

    def fake_videocapture(index):
        opened_indices.append(index)
        return captures.get(index, FakeCapture(False))

    def fake_imwrite(path, frame):
        saved["path"] = path
        saved["frame"] = frame
        Path(path).write_bytes(b"camera-image")
        return True

    fake_cv2.VideoCapture = fake_videocapture
    fake_cv2.imwrite = fake_imwrite
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    result = capture_camera_image()

    assert opened_indices == [0, 1]
    assert saved["frame"] is captures[1]._frame
    assert captures[0].released is True
    assert captures[1].released is True
    assert result["ok"] is True
    assert result["path"].exists()


def test_capture_camera_image_skips_blank_virtual_camera_when_std_is_numpy_scalar(monkeypatch, artifact_dir):
    captures = {
        0: FakeCapture(True, FakeFrame(FakeNumpyScalar(0.0))),
        1: FakeCapture(True, FakeFrame(FakeNumpyScalar(18.0))),
    }
    opened_indices = []
    saved = {}

    fake_cv2 = types.SimpleNamespace()

    def fake_videocapture(index):
        opened_indices.append(index)
        return captures.get(index, FakeCapture(False))

    def fake_imwrite(path, frame):
        saved["frame"] = frame
        Path(path).write_bytes(b"camera-image")
        return True

    fake_cv2.VideoCapture = fake_videocapture
    fake_cv2.imwrite = fake_imwrite
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    result = capture_camera_image()

    assert opened_indices == [0, 1]
    assert saved["frame"] is captures[1]._frame
    assert result["ok"] is True


def test_capture_camera_image_raises_when_only_blank_cameras_exist(monkeypatch, artifact_dir):
    captures = {
        0: FakeCapture(True, FakeFrame(0.0)),
        1: FakeCapture(True, FakeFrame(0.0)),
    }

    fake_cv2 = types.SimpleNamespace(
        VideoCapture=lambda index: captures.get(index, FakeCapture(False)),
        imwrite=lambda path, frame: True,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    with pytest.raises(AgentFeatureError) as exc:
        capture_camera_image()

    assert exc.value.error == "camera_capture_failed"
