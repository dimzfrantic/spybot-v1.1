from functools import wraps

from flask import jsonify, request

from config import AGENT_TOKEN


def _is_authorized(req) -> bool:
    supplied = req.headers.get("X-Agent-Token", "")
    return bool(AGENT_TOKEN) and supplied == AGENT_TOKEN


def require_agent_token(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not _is_authorized(request):
            return jsonify({
                "ok": False,
                "error": "unauthorized",
                "message": "Invalid agent token",
            }), 401
        return view_func(*args, **kwargs)

    return wrapper
