#!/usr/bin/env python3
"""Local integration tests for Vercel API handlers."""
import json
import os
import sys
from io import BytesIO
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))

REF = open(os.path.join(os.path.dirname(__file__), "examples/reference.tex")).read()
INP = open(os.path.join(os.path.dirname(__file__), "examples/input.tex")).read()


def mock_handler(module_name, method, body=None):
    import importlib

    mod = importlib.import_module(module_name)
    handler = mod.handler

    request = MagicMock()
    request.headers = {"Content-Length": str(len(body.encode()) if body else 0)}
    request.rfile = BytesIO(body.encode() if body else b"")
    request.command = method

    response_body = BytesIO()
    request.wfile = response_body

    if method == "GET":
        handler.do_GET(request)
    elif method == "POST":
        handler.do_POST(request)
    elif method == "OPTIONS":
        handler.do_OPTIONS(request)

    return json.loads(response_body.getvalue().decode())


def main():
    print("=== GET /api/health ===")
    health = mock_handler("health", "GET")
    assert health["status"] == "ok", health
    print("OK:", health["status"])

    print("\n=== POST /api/count ===")
    count = mock_handler(
        "count",
        "POST",
        json.dumps({"reference_latex": REF, "input_latex": INP}),
    )
    assert "input" in count and "limits" in count, count
    assert count["limits"]["heading"] == 94
    assert count["limits"]["body"] == 310
    print("OK: limits", count["limits"], "input", count["input"], "fits", count["fits"])

    if not os.environ.get("GEMINI_API_KEY"):
        print("\n=== POST /api/shorten === SKIPPED (no GEMINI_API_KEY)")
        print("\nAll local tests passed (count + health).")
        return

    print("\n=== POST /api/shorten ===")
    shorten = mock_handler(
        "shorten",
        "POST",
        json.dumps(
            {
                "reference_latex": REF,
                "input_latex": INP,
                "sibling_verbs": ["Optimized", "Deployed", "Redesigned"],
            }
        ),
    )
    assert "text" in shorten and shorten.get("fits") is True, shorten
    assert "\\begin{tabularx}" in shorten["text"]
    print("OK: new", shorten["new"], "fits", shorten["fits"])
    print("notes:", shorten["notes"])
    print("\nAll local tests passed.")


if __name__ == "__main__":
    main()
