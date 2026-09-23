"""TypeSafe Jev judgments. Jev returns types and probabilities, not prose."""
import os

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

REVIEW_QUESTIONS = {
    "risk": Score(
        instructions="Overall merge risk for this change",
        criteria=[
            "Low — safe, narrow, well-tested change",
            "Moderate — some uncertainty or medium surface area",
            "High — risky patterns, large blast radius, or weak coverage",
            "Critical — likely to break production or security posture",
        ],
    ),
    "review_depth": Choice(
        instructions="How deep should a human reviewer go on this change?",
        criteria={
            "skim": "Quick glance is enough; change is small and obvious",
            "standard": "Normal careful review of logic and tests",
            "deep": "Needs thorough review of architecture, edge cases, and side effects",
        },
    ),
    "needs_design": Noul(instructions="Does this change need a design or architecture discussion before merge?"),
    "needs_security": Noul(instructions="Does this change need dedicated security review before merge?"),
    "merge_blocker": Noul(instructions="Should merge be blocked until issues in this change are fixed?"),
    "missing_tests": Score(
        instructions="How severe is the missing or weak test coverage?",
        criteria=[
            "Adequate tests for the change",
            "Some gaps, but core paths covered",
            "Important paths lack tests",
            "Critical behavior is untested",
        ],
    ),
    "docs_debt": Score(
        instructions="How much documentation debt does this change introduce or leave?",
        criteria=[
            "Docs are sufficient",
            "Minor docs gaps",
            "Notable missing docs or comments",
            "Serious docs debt that will confuse maintainers",
        ],
    ),
    "blast_radius": Score(
        instructions="How wide could a bug in this change spread?",
        criteria=[
            "Isolated to a small local path",
            "Affects one feature area",
            "Could impact multiple modules or users",
            "Could cascade across the system or infra",
        ],
    ),
    "verdict": Choice(
        instructions="Final verdict for this change",
        criteria={
            "approve_with_nits": "Safe to merge; nits can land follow-up",
            "request_changes": "Needs fixes before merge",
            "block": "Do not merge until major issues are resolved",
        },
    ),
}


def _client() -> TypeSafeClient:
    if not (os.environ.get("TYPESAFE_API_KEY") or "").strip():
        raise RuntimeError("TYPESAFE_API_KEY is not set.")
    return TypeSafeClient()


def _dump_answer(answer) -> dict:
    data = {"type": getattr(answer, "type", None)}
    for field in ("noul", "choice", "confidence", "score"):
        if hasattr(answer, field):
            value = getattr(answer, field)
            if value is not None:
                data[field] = value
    return data


def _run(state: str, questions: dict) -> dict:
    with _client() as client:
        response = client.system_one(model="jev-latest", state=state[:28000], questions=questions)
    answers = {}
    raw = getattr(response, "answers", None) or {}
    if isinstance(raw, dict) and raw:
        for key, answer in raw.items():
            answers[key] = answer if isinstance(answer, dict) else _dump_answer(answer)
    else:
        for key in questions:
            bucket = None
            for attr in ("choices", "nouls", "scores"):
                group = getattr(response, attr, None) or {}
                if key in group:
                    bucket = group[key]
                    break
            if bucket is not None:
                answers[key] = _dump_answer(bucket)
    return {"model": getattr(response, "model", "jev-latest"), "answers": answers}


def review_change(title: str, body: str, diff: str) -> dict:
    state = f"TITLE\n{title}\n\nBODY\n{body[:4000]}\n\nDIFF\n{diff[:20000]}"
    return _run(state, REVIEW_QUESTIONS)


def choose_landmark(candidates: list[str]) -> dict:
    """Ask which landmark a human should open first. Candidates are real paths."""
    options = candidates[:12]
    if len(options) < 2:
        return {"model": None, "answers": {}}
    criteria = {path: "A real file in this repository" for path in options}
    questions = {
        "open_first": Choice(
            instructions="Which file should a human open first to understand this repository?",
            criteria=criteria,
        )
    }
    state = "Landmark files:\n" + "\n".join(options)
    return _run(state, questions)


def spam_signal(title: str, body: str) -> dict:
    """One noul: is this candidate noise? Only call this for already-flagged items."""
    questions = {
        "spam": Noul(
            instructions="Is this GitHub issue or comment spam, a drive-by, or repeated noise rather than a real engineering discussion?"
        )
    }
    state = f"TITLE\n{title[:300]}\n\nBODY\n{body[:2000]}"
    return _run(state, questions)


def finding_noul(title: str, evidence: str) -> dict:
    """One noul on a candidate the deterministic pass already found."""
    questions = {
        "real_issue": Noul(
            instructions="Is this a real security or license issue a human should look at, rather than a test fixture, a comment, or a placeholder?"
        )
    }
    state = f"FINDING\n{title[:240]}\n\nEVIDENCE\n{evidence[:2000]}"
    return _run(state, questions)


def needs_second_reader(review: dict) -> bool:
    answers = (review or {}).get("answers") or {}
    depth = (answers.get("review_depth") or {}).get("choice")
    security = (answers.get("needs_security") or {}).get("noul") or 0
    confidence = (answers.get("verdict") or {}).get("confidence")
    if depth == "deep":
        return True
    if isinstance(security, (int, float)) and security >= 0.55:
        return True
    if isinstance(confidence, (int, float)) and confidence < 0.55:
        return True
    return False
