#!/usr/bin/env python3
"""Local integration tests for the FastAPI Vercel handler."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))

from fastapi.testclient import TestClient
from index import app

REF = open(os.path.join(os.path.dirname(__file__), "examples/reference.tex")).read()
INP = open(os.path.join(os.path.dirname(__file__), "examples/input.tex")).read()

client = TestClient(app)


def main():
    print("=== GET /api/health ===")
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    print("OK:", data["status"])

    print("\n=== POST /api/count ===")
    r = client.post(
        "/api/count",
        json={"reference_latex": REF, "input_latex": INP},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limits"]["heading"] == 94
    assert data["limits"]["body"] == 310
    print("OK: limits", data["limits"], "input", data["input"], "fits", data["fits"])

    if not os.environ.get("GEMINI_API_KEY"):
        print("\n=== POST /api/shorten === SKIPPED (no GEMINI_API_KEY)")
        print("\nAll local tests passed (health + count).")
        return

    print("\n=== POST /api/shorten ===")
    r = client.post(
        "/api/shorten",
        json={
            "reference_latex": REF,
            "input_latex": INP,
            "sibling_verbs": ["Optimized", "Deployed", "Redesigned"],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("fits") is True, data
    assert "\\begin{tabularx}" in data["text"]
    print("OK: new", data["new"], "fits", data["fits"])
    print("notes:", data["notes"])
    print("\nAll local tests passed.")


if __name__ == "__main__":
    main()
