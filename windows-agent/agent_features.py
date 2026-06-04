import mimetypes
import os
import string
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, cast

from config import BASE_DIR

ARTIFACT_DIR = BASE_DIR / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)
CAMERA_SCAN_LIMIT = 6
CAMERA_MIN_FRAME_STDDEV = 5.0


class AgentFeatureError(Exception):
    def __init__(self, error: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _detect_mimetype(path: Path) -> str:
    mimetype, _ = mimetypes.guess_type(str(path))
    return mimetype or "application/octet-stream"


def _resolve_target_path(target_path: str) -> Path:
    if not target_path:
        raise AgentFeatureError("missing_path", "Parameter path wajib diisi", 400)

    expanded = os.path.expandvars(target_path.strip())
    expanded = os.path.expanduser(expanded)
    path = Path(expanded)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _iter_windows_drives():
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:/")
        if drive.exists():
            yield drive


def get_explorer_root_listing() -> dict:
    drives = [
        {
            "name": drive.drive or str(drive),
            "path": str(drive),
            "type": "dir",
        }
        for drive in _iter_windows_drives()
    ]
    return {
        "ok": True,
        "path": "drives:/",
        "items": drives,
    }


def list_directory(target_path: Optional[str]) -> dict:
    if not target_path:
        return get_explorer_root_listing()

    path = _resolve_target_path(target_path)
    if not path.exists():
        raise AgentFeatureError("path_not_found", f"Path tidak ditemukan: {path}", 404)
    if not path.is_dir():
        raise AgentFeatureError("not_a_directory", f"Path bukan folder: {path}", 400)

    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except PermissionError as exc:
        raise AgentFeatureError("access_denied", f"Akses folder ditolak: {path}", 403) from exc
    except OSError as exc:
        raise AgentFeatureError("directory_read_failed", f"Gagal membaca folder: {path}", 500) from exc

    items = []
    for child in children:
        entry = {
            "name": child.name,
            "path": str(child),
            "type": "dir" if child.is_dir() else "file",
        }
        if child.is_file():
            try:
                entry["size"] = child.stat().st_size
            except OSError:
                entry["size"] = None
        items.append(entry)

    return {
        "ok": True,
        "path": str(path),
        "items": items,
    }


def prepare_download_file(target_path: str) -> dict:
    path = _resolve_target_path(target_path)
    if not path.exists():
        raise AgentFeatureError("path_not_found", f"File tidak ditemukan: {path}", 404)
    if not path.is_file():
        raise AgentFeatureError("not_a_file", f"Path bukan file: {path}", 400)

    return {
        "ok": True,
        "path": path,
        "filename": path.name,
        "mimetype": _detect_mimetype(path),
        "size": path.stat().st_size,
    }


def capture_screenshot() -> dict:
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise AgentFeatureError(
            "dependency_missing",
            "Pillow belum terpasang untuk fitur screenshot",
            500,
        ) from exc

    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        raise AgentFeatureError(
            "screenshot_failed",
            f"Gagal mengambil screenshot: {exc}",
            500,
        ) from exc

    output_path = ARTIFACT_DIR / f"screenshot-{_timestamp_slug()}.jpg"
    image.convert("RGB").save(output_path, format="JPEG", quality=90)
    return {
        "ok": True,
        "path": output_path,
        "filename": output_path.name,
        "mimetype": "image/jpeg",
    }


def capture_camera_image() -> dict:
    try:
        import cv2
    except ImportError as exc:
        raise AgentFeatureError(
            "dependency_missing",
            "opencv-python belum terpasang untuk fitur camera",
            500,
        ) from exc

    selected_frame = None
    found_camera = False

    for index in range(CAMERA_SCAN_LIMIT):
        camera = cv2.VideoCapture(index)
        if not camera.isOpened():
            camera.release()
            continue

        found_camera = True
        try:
            ok, frame = camera.read()
        finally:
            camera.release()

        if not ok or frame is None:
            continue

        frame_std = getattr(frame, "std", None)
        if callable(frame_std):
            try:
                frame_std_value = float(cast(float, frame_std()))
                if frame_std_value < CAMERA_MIN_FRAME_STDDEV:
                    continue
            except Exception:
                pass

        selected_frame = frame
        break

    if not found_camera:
        raise AgentFeatureError("camera_unavailable", "Camera tidak tersedia atau sedang dipakai", 503)

    if selected_frame is None:
        raise AgentFeatureError("camera_capture_failed", "Gagal mengambil gambar dari camera", 500)

    output_path = ARTIFACT_DIR / f"camera-{_timestamp_slug()}.jpg"
    if not cv2.imwrite(str(output_path), selected_frame):
        raise AgentFeatureError("camera_write_failed", "Gagal menyimpan hasil camera", 500)

    return {
        "ok": True,
        "path": output_path,
        "filename": output_path.name,
        "mimetype": "image/jpeg",
    }
