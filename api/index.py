import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tex_char_count import parse_cc_limits, process_latex

app = FastAPI(title="tex-char-count")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LatexRequest(BaseModel):
    input_latex: str
    reference_latex: str


class ShortenRequest(LatexRequest):
    sibling_verbs: Optional[List[str]] = None


def _require_limits(reference_latex: str):
    limits = parse_cc_limits(reference_latex)
    if not limits:
        raise HTTPException(
            status_code=400,
            detail=(
                "reference_latex must include a CC comment "
                "(% heading CC: orig=..., new=... | body CC: ...)"
            ),
        )
    return limits


@app.get("/api")
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "tex-char-count",
        "endpoints": {
            "GET /api/health": "health check",
            "POST /api/count": "count heading/body chars vs reference limits",
            "POST /api/shorten": "shorten LaTeX bullet to fit reference limits",
        },
    }


@app.post("/api/count")
def count(req: LatexRequest):
    limits = _require_limits(req.reference_latex)
    result = process_latex(req.input_latex, req.reference_latex, count_only=True)
    return {
        "limits": {"heading": limits.heading, "body": limits.body},
        "input": {"heading": result.orig.heading, "body": result.orig.body},
        "fits": (
            result.orig.heading <= limits.heading
            and result.orig.body <= limits.body
        ),
        "notes": result.notes,
        "text": result.text,
    }


@app.post("/api/shorten")
def shorten(req: ShortenRequest):
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    limits = _require_limits(req.reference_latex)
    result = process_latex(
        req.input_latex,
        req.reference_latex,
        sibling_verbs=req.sibling_verbs,
    )
    payload = result.to_dict()
    payload["limits"] = {"heading": limits.heading, "body": limits.body}
    payload["fits"] = (
        result.new.heading <= limits.heading and result.new.body <= limits.body
    )
    return payload
