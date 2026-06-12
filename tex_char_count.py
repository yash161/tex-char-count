import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def _visible_text(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"(?<!\\)%.*$", "", cleaned, flags=re.MULTILINE)

    inline_cmds = ("textbf", "textit", "emph", "texttt", "underline", "textrm")
    pattern = r"\\(?:" + "|".join(inline_cmds) + r")\{([^{}]*)\}"
    while re.search(pattern, cleaned):
        cleaned = re.sub(pattern, r"\1", cleaned)

    cleaned = re.sub(r"\\item\b\s*", "", cleaned)
    cleaned = re.sub(r"\\\\", " ", cleaned)
    cleaned = re.sub(r"\\%", "%", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?(\{[^{}]*\})*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def tex_char_count(text: str, *, strip_latex: bool = True, count_spaces: bool = True) -> int:
    """
    Count visible characters in TeX/LaTeX text.

    With strip_latex=True (default), LaTeX commands are removed and only the
    visible/rendered text is counted — useful for resume bullet limits.

    Heading counts include spaces; body counts exclude spaces (matches resume CC).
    """
    if not strip_latex:
        return len(text)

    visible = _visible_text(text)
    if not count_spaces:
        visible = visible.replace(" ", "")
    return len(visible)


@dataclass
class BulletParts:
    heading: str
    body: str
    comment: str


@dataclass
class BulletCounts:
    heading: int
    body: int

    @property
    def total(self) -> int:
        return self.heading + self.body


def _split_trailing_comment(text: str) -> Tuple[str, str]:
    """Split trailing LaTeX comment, ignoring escaped \\% in the body."""
    match = re.search(r"(?<!\\)%.*$", text, flags=re.MULTILINE)
    if not match:
        return text.strip(), ""
    comment = match.group(0).rstrip()
    main = text[: match.start()].strip()
    return main, comment


def parse_bullet(text: str) -> BulletParts:
    """Split \\item \\textbf{heading} \\\\ body [% comment]."""
    text, comment = _split_trailing_comment(text)

    match = re.match(
        r"\\item\s*\\textbf\{([^}]*)\}\s*\\\\\s*(.*)",
        text.strip(),
        re.DOTALL,
    )
    if not match:
        raise ValueError("Expected \\item \\textbf{...} \\\\ body format")

    return BulletParts(
        heading=match.group(1),
        body=match.group(2).strip(),
        comment=comment.rstrip(),
    )


def count_bullet(text: str) -> BulletCounts:
    """Heading CC with spaces; body CC without spaces."""
    parts = parse_bullet(text)
    return BulletCounts(
        heading=tex_char_count(parts.heading, count_spaces=True),
        body=tex_char_count(parts.body, count_spaces=False),
    )


def format_bullet(heading: str, body: str, counts: BulletCounts, orig: BulletCounts) -> str:
    comment = (
        f"% heading CC: orig={orig.heading}, new={counts.heading} "
        f"| body CC: orig={orig.body}, new={counts.body}"
    )
    return f"\\item \\textbf{{{heading}}} \\\\\n{body} {comment}"


def parse_cc_limits(text: str) -> Optional[BulletCounts]:
    """Read target limits from trailing % heading CC: ... comment."""
    match = re.search(
        r"heading CC:\s*orig=(\d+),\s*new=(\d+)\s*\|\s*body CC:\s*orig=(\d+),\s*new=(\d+)",
        text,
    )
    if not match:
        return None
    return BulletCounts(heading=int(match.group(2)), body=int(match.group(4)))


_ITEM_RE = re.compile(
    r"(\\item\s*\\textbf\{[^}]*\}\s*\\\\\s*.*?)(?=\n\s*\\end\{itemize\}|\Z)",
    re.DOTALL,
)


@dataclass
class LatexBlock:
    """Full LaTeX around a single \\item bullet."""

    prefix: str
    bullet: str
    suffix: str

    def wrap(self, bullet: str) -> str:
        return f"{self.prefix}{bullet}\n{self.suffix}"


def extract_bullet(text: str) -> str:
    """Pull the \\item ... bullet out of a full LaTeX block or return as-is."""
    text = text.strip()
    match = _ITEM_RE.search(text)
    if match:
        return match.group(1).strip()
    if text.startswith(r"\item"):
        return text
    raise ValueError("No \\item \\textbf{...} \\\\ bullet found in input")


def extract_latex_block(text: str) -> LatexBlock:
    """Split full tabularx/itemize LaTeX into prefix + bullet + suffix."""
    text = text.strip()
    match = _ITEM_RE.search(text)
    if not match:
        return LatexBlock(prefix="", bullet=extract_bullet(text), suffix="")
    return LatexBlock(
        prefix=text[: match.start()],
        bullet=match.group(1).strip(),
        suffix=text[match.end() :].lstrip("\n"),
    )


def wrap_in_latex(block: LatexBlock, bullet: str) -> str:
    """Put a bullet back inside the original LaTeX wrapper."""
    if not block.prefix and not block.suffix:
        return bullet
    return block.wrap(bullet)


def replace_bullet_in_latex(full_latex: str, new_bullet: str) -> str:
    """Swap the \\item bullet inside a full LaTeX block, keeping the wrapper."""
    match = _ITEM_RE.search(full_latex)
    if not match:
        return new_bullet
    return full_latex[: match.start()] + new_bullet + full_latex[match.end() :]


@dataclass
class ShortenResult:
    text: str
    orig: BulletCounts
    new: BulletCounts
    method: str
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "orig": {"heading": self.orig.heading, "body": self.orig.body},
            "new": {"heading": self.new.heading, "body": self.new.body},
            "method": self.method,
            "notes": self.notes,
        }


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _call_gemini(
    *,
    system: str,
    messages: List[Dict],
    api_key: str,
    model: str,
) -> str:
    payload = json.dumps(
        {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": messages,
            "generationConfig": {"temperature": 0.2},
        }
    ).encode()

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"Gemini API error ({exc.code}): {detail}") from exc

    return body["candidates"][0]["content"]["parts"][0]["text"]


def _counts_from_latex(text: str) -> Tuple[BulletCounts, BulletParts]:
    cleaned = _strip_code_fence(text)
    bullet = extract_bullet(cleaned)
    parts = parse_bullet(bullet)
    counts = BulletCounts(
        heading=tex_char_count(parts.heading, count_spaces=True),
        body=tex_char_count(parts.body, count_spaces=False),
    )
    return counts, parts


def _fits_limits(counts: BulletCounts, max_heading: int, max_body: int) -> bool:
    return counts.heading <= max_heading and counts.body <= max_body


def opening_verb(body: str) -> str:
    """First visible word of the bullet body."""
    visible = _visible_text(body)
    match = re.match(r"([A-Za-z]+)", visible)
    return match.group(1) if match else ""


def _has_em_dash(text: str) -> bool:
    return bool(re.search(r"---|—|--", text))


def _style_issues(parts: BulletParts, sibling_verbs: List[str]) -> List[str]:
    issues = []
    body_visible = _visible_text(parts.body)

    if _has_em_dash(parts.body):
        issues.append("body contains an em dash (--- or --); use a comma or semicolon instead")

    verb = opening_verb(parts.body)
    normalized_siblings = {v.strip().lower() for v in sibling_verbs if v.strip()}
    if verb and verb.lower() in normalized_siblings:
        siblings = ", ".join(sorted(normalized_siblings))
        issues.append(
            f"opening verb '{verb}' repeats a sibling bullet ({siblings}); "
            "keep the original opening verb or pick one not already used"
        )

    if re.search(r"\b(colour|behaviour|optimise|organise|centre|favour)\b", body_visible, re.I):
        issues.append("use American English spelling (color, behavior, optimize, etc.)")

    return issues


def _build_system_prompt(sibling_verbs: List[str], *, full_block: bool) -> str:
    siblings = ", ".join(sibling_verbs) if sibling_verbs else "(none provided)"
    output_fmt = (
        "Return the COMPLETE tailored LaTeX block (tabularx, minipage, itemize, everything). "
        "Keep every \\begin/\\end, option, blank line, and indentation identical to the input. "
        "Only delete extra words inside the \\item bullet."
        if full_block
        else "Format: \\item \\textbf{heading} \\\\ body"
    )
    return f"""You are a LaTeX resume editor. Output raw LaTeX only — no markdown fences, no explanation.

{output_fmt}

EDITING RULES (critical):
- Remove ONLY the minimum extra/redundant words needed to fit the limit.
- Do NOT over-trim. Do NOT rewrite sentences. Do NOT swap synonyms.
- Delete filler words only, not rephrase.
- Keep \\textbf{{}} on the same words unless that exact word is deleted.
- Do not change facts, numbers, or meaning.
- American English only.
- No em dashes (no --- or --); use commas or semicolons.
- Opening verb must NOT repeat sibling bullets: {siblings}
- Keep the original opening verb when possible."""


def _build_trim_prompt(
    text: str,
    orig: BulletCounts,
    max_heading: int,
    max_body: int,
    sibling_verbs: List[str],
    *,
    full_latex: Optional[str] = None,
) -> str:
    siblings = ", ".join(sibling_verbs) if sibling_verbs else "(none)"
    heading_over = max(0, orig.heading - max_heading)
    body_over = max(0, orig.body - max_body)
    bullet = extract_bullet(text) if not text.strip().startswith(r"\item") else text
    verb = opening_verb(parse_bullet(bullet).body)
    source = full_latex if full_latex else text
    output_instruction = (
        "Return the complete tailored LaTeX block below with only extra words removed."
        if full_latex
        else "Return only the shortened \\item bullet."
    )
    return f"""{output_instruction}

Limits (remove the MINIMUM words to fit — do not over-trim):
- heading: {orig.heading} → <= {max_heading}  (remove ~{heading_over} chars, spaces count)
- body: {orig.body} → <= {max_body}  (remove ~{body_over} chars, spaces do NOT count)

Style:
- American English, no em dashes
- Opening verb must differ from siblings: {siblings}
- Keep opening verb "{verb}" — do NOT change it

Rules:
- Delete filler/redundant words only (e.g. "setup", "server", repeated adjectives)
- Do NOT rewrite sentences or swap synonyms
- Keep as much original wording as possible
- Stay as close to the limit as possible without exceeding it
- Raw LaTeX only. No ``` markdown. No commentary.

{source}"""


def _feedback_message(
    counts: BulletCounts,
    max_heading: int,
    max_body: int,
    attempt: int,
    style_issues: Optional[List[str]] = None,
) -> str:
    issues = list(style_issues or [])
    if counts.heading > max_heading:
        over = counts.heading - max_heading
        issues.append(
            f"heading is {counts.heading} but must be <= {max_heading} "
            f"(delete {over} extra heading chars; spaces count)"
        )
    if counts.body > max_body:
        over = counts.body - max_body
        issues.append(
            f"body is {counts.body} but must be <= {max_body} "
            f"(delete {over} extra body chars; spaces do NOT count)"
        )

    problem_lines = "\n".join(f"- {issue}" for issue in issues)
    return f"""REJECTED — attempt {attempt}.

Problems:
{problem_lines}

Delete only extra words. Do not rephrase. Keep \\textbf{{}} on surviving words.
Return the complete tailored LaTeX block (same structure as input). Raw LaTeX only."""


def _load_sibling_verbs(path: Optional[str] = None) -> List[str]:
    path = path or os.environ.get(
        "SIBLING_VERBS_FILE",
        os.path.join(os.path.dirname(__file__), "examples", "sibling_verbs.txt"),
    )
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def shorten_bullet_to_fit(
    text: str,
    *,
    max_heading: int,
    max_body: int,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_attempts: Optional[int] = None,
    latex_block: Optional[LatexBlock] = None,
    sibling_verbs: Optional[List[str]] = None,
    full_latex: Optional[str] = None,
) -> ShortenResult:
    """
    Shorten a resume bullet so heading <= max_heading and body <= max_body.

    Uses a feedback loop: if output exceeds limits, sends it back to the LLM
    with exact counts and what to fix, until limits are met or max_attempts.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is required. Export it: export GEMINI_API_KEY=your-key"
        )

    model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    max_attempts = max_attempts or int(os.environ.get("MAX_RL_ATTEMPTS", "5"))
    sibling_verbs = sibling_verbs if sibling_verbs is not None else _load_sibling_verbs()
    orig = count_bullet(text)

    use_full_block = bool(full_latex and (latex_block and (latex_block.prefix or latex_block.suffix)))
    system = _build_system_prompt(sibling_verbs, full_block=use_full_block)
    initial_prompt = _build_trim_prompt(
        text,
        orig,
        max_heading,
        max_body,
        sibling_verbs,
        full_latex=full_latex if use_full_block else None,
    )

    messages = [{"role": "user", "parts": [{"text": initial_prompt}]}]
    notes: list[str] = []
    result_text = ""
    counts = orig
    new_parts = parse_bullet(text)

    for attempt in range(1, max_attempts + 1):
        raw = _call_gemini(system=system, messages=messages, api_key=api_key, model=model)
        result_text = _strip_code_fence(raw)
        counts, new_parts = _counts_from_latex(result_text)
        style = _style_issues(new_parts, sibling_verbs)
        fits_counts = _fits_limits(counts, max_heading, max_body)
        heading_under = max_heading - counts.heading
        body_under = max_body - counts.body
        if fits_counts and (heading_under > 15 or body_under > 25):
            style.append(
                f"over-trimmed: heading {heading_under} chars under limit, "
                f"body {body_under} chars under limit; "
                "you deleted too much — restore wording, delete fewer words"
            )
        fits = fits_counts and not style

        if fits:
            notes.append(
                f"Attempt {attempt}: accepted "
                f"(heading={counts.heading}, body={counts.body}, verb={opening_verb(new_parts.body)})."
            )
            break

        reason = []
        if not _fits_limits(counts, max_heading, max_body):
            reason.append(f"over limit h={counts.heading} b={counts.body}")
        if style:
            reason.append("style: " + "; ".join(style))
        notes.append(f"Attempt {attempt}: rejected ({', '.join(reason)}).")

        if attempt == max_attempts:
            notes.append(f"Gave up after {max_attempts} attempts.")
            break

        messages.append({"role": "model", "parts": [{"text": raw}]})
        messages.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": _feedback_message(
                            counts, max_heading, max_body, attempt, style
                        )
                    }
                ],
            }
        )

    bullet = format_bullet(new_parts.heading, new_parts.body, counts, orig)
    api_block = extract_latex_block(result_text)
    if use_full_block and (api_block.prefix or api_block.suffix):
        formatted = replace_bullet_in_latex(result_text, bullet)
    elif latex_block and (latex_block.prefix or latex_block.suffix):
        formatted = wrap_in_latex(latex_block, bullet)
    else:
        formatted = bullet
    return ShortenResult(
        text=formatted,
        orig=orig,
        new=counts,
        method="gemini-rl",
        notes=notes,
    )


def process_latex(
    input_latex: str,
    reference_latex: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_attempts: Optional[int] = None,
    count_only: bool = False,
    sibling_verbs: Optional[List[str]] = None,
) -> ShortenResult:
    """
    Shorten input_latex bullet to fit limits from reference_latex CC comment.

    Both can be full tabularx/itemize blocks or plain \\item bullets.
    """
    limits = parse_cc_limits(reference_latex)
    if not limits:
        raise ValueError(
            "Reference must include a CC comment like: "
            "% heading CC: orig=94, new=94 | body CC: orig=310, new=310"
        )

    input_block = extract_latex_block(input_latex)
    bullet = input_block.bullet
    orig = count_bullet(bullet)

    if count_only:
        ref_counts = count_bullet(extract_bullet(reference_latex))
        return ShortenResult(
            text=input_block.wrap(bullet),
            orig=orig,
            new=orig,
            method="count-only",
            notes=[
                f"Input: heading={orig.heading}, body={orig.body}",
                f"Reference limits: heading<={limits.heading}, body<={limits.body}",
                f"Reference actual: heading={ref_counts.heading}, body={ref_counts.body}",
            ],
        )

    has_wrapper = bool(input_block.prefix or input_block.suffix)
    return shorten_bullet_to_fit(
        bullet,
        max_heading=limits.heading,
        max_body=limits.body,
        api_key=api_key,
        model=model,
        max_attempts=max_attempts,
        latex_block=input_block if has_wrapper else None,
        sibling_verbs=sibling_verbs,
        full_latex=input_latex if has_wrapper else None,
    )


CICD_REFERENCE = r"""\begin{tabularx}{\linewidth}{@{}l r@{}}
\begin{minipage}[t]{\linewidth}
\begin{itemize}[nosep, after=\strut, leftmargin=2em]

\item \textbf{CI/CD Scaling GitHub Actions Optimizations (2025): Python, GitHub Actions, Bazel, CI/CD, Linux} \\
Optimized \textbf{CI/CD} test automation pipelines using \textbf{Python} and Bazel with \textbf{Shell} scripting, reducing build and test cycle time by \textbf{15\%} and improving diagnostic coverage; integrated Datadog to visualize system health metrics, enhancing observability across distributed \textbf{Linux}-based server environments handling millions of daily automated test and validation runs. % heading CC: orig=94, new=94 | body CC: orig=310, new=310

\end{itemize}
\end{minipage}
\end{tabularx}"""

K8S_SAMPLE = r"""\begin{tabularx}{\linewidth}{@{}l r@{}}
\begin{minipage}[t]{\linewidth}
\begin{itemize}[nosep, after=\strut, leftmargin=2em]

\item \textbf{Kubernetes EKS CI/CD Pipelines Deployment (Dec 2024): Python, Terraform, Jenkins, AWS EKS, Docker, Linux} \\
Deployed containerized \textbf{Python} application on \textbf{AWS} EKS using \textbf{Terraform} for server infrastructure provisioning and Jenkins for \textbf{CI/CD} automation; configured \textbf{Docker}-based build pipelines, test validation procedures, and rolling update strategies on \textbf{Linux} nodes following \textbf{Git} branching workflows, achieving zero-downtime deployments across environments. % heading CC: orig=104, new=104 | body CC: orig=321, new=321

\end{itemize}
\end{minipage}
\end{tabularx}"""


def _read_latex_arg(path: Optional[str], default: str) -> str:
    if path is None:
        return default
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count and shorten LaTeX resume bullets to fit a reference CC limit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Count only — check your bullet vs reference limits
  python3 tex_char_count.py --count-only -r reference.tex -i my_bullet.tex

  # Shorten your bullet to fit reference limits
  export GEMINI_API_KEY=your-key
  python3 tex_char_count.py -r reference.tex -i my_bullet.tex

  # Write output to file
  python3 tex_char_count.py -r reference.tex -i my_bullet.tex -o output.tex

Files can be full tabularx/itemize blocks or just the \\item line.
The reference file must have a CC comment with target limits (the "new=" values).
        """,
    )
    parser.add_argument(
        "-r", "--reference",
        help="Reference LaTeX with CC limits (default: built-in CI/CD sample)",
    )
    parser.add_argument(
        "-i", "--input",
        help="Your LaTeX bullet to shorten (default: built-in K8s sample)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write result to file instead of stdout",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Only show character counts, do not call Gemini",
    )
    parser.add_argument(
        "--sibling-verbs",
        help="Comma-separated opening verbs used by other bullets (e.g. Optimized,Deployed,Redesigned)",
    )
    args = parser.parse_args()

    sibling_verbs: Optional[List[str]] = None
    if args.sibling_verbs:
        sibling_verbs = [v.strip() for v in args.sibling_verbs.split(",") if v.strip()]

    reference = _read_latex_arg(args.reference, CICD_REFERENCE)
    input_latex = _read_latex_arg(args.input, K8S_SAMPLE)
    limits = parse_cc_limits(reference)

    print("Reference limits (from CC comment):")
    print(f"  heading CC: <= {limits.heading if limits else '?'}")
    print(f"  body CC:    <= {limits.body if limits else '?'}")
    print()

    if args.count_only:
        result = process_latex(input_latex, reference, count_only=True)
        for note in result.notes:
            print(note)
        print()
        print(result.text)
        return

    if not os.environ.get("GEMINI_API_KEY"):
        print("Set GEMINI_API_KEY to shorten:")
        print("  export GEMINI_API_KEY=your-key")
        sys.exit(1)

    result = process_latex(input_latex, reference, sibling_verbs=sibling_verbs)
    print("Output counts:")
    print(f"  heading CC: orig={result.orig.heading}, new={result.new.heading}")
    print(f"  body CC:    orig={result.orig.body}, new={result.new.body}")
    for note in result.notes:
        print(f"  note: {note}")
    print()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.text)
        print(f"Written to {args.output}")
    else:
        print(result.text)


if __name__ == "__main__":
    main()
