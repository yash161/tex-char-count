import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional, Tuple

ROOT = os.path.join(os.path.dirname(__file__), "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def read_json_body(handler: BaseHTTPRequestHandler) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return None, "Request body is required"
    try:
        raw = handler.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "JSON body must be an object"
    return data, None


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    for key, value in CORS_HEADERS.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_options(handler: BaseHTTPRequestHandler) -> bool:
    if handler.command == "OPTIONS":
        send_json(handler, 200, {"ok": True})
        return True
    return False


def require_fields(data: Dict[str, Any], fields: Tuple[str, ...]) -> Optional[str]:
    missing = [f for f in fields if not data.get(f)]
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    return None


def error_response(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    send_json(handler, status, {"error": message})


def handle_exception(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    traceback.print_exc()
    error_response(handler, 500, str(exc))
