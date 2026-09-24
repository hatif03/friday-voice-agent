"""One check every review has to clear before Friday may sound sure.

Jev owns the thresholds. A Gateway draft, a K2 read, and a Vertex read all
meet this function. A missing second reader is not a softer bar.
"""
from __future__ import annotations

MERGE_BLOCKER_DANGER = 0.65
CONFIDENCE_FLOOR = 0.55


def _answer(jev: dict, key: str) -> dict:
    return ((jev or {}).get("answers") or {}).get(key) or {}


def validate_review(
    *,
    jev: dict | None,
    draft: dict | None,
    known_paths: set[str],
    second_reads: list[dict] | None = None,
    second_reads_required: bool = False,
) -> dict:
    """Return cleared, tone, say, and the reasons a human can inspect."""
    reasons: list[str] = []
    jev = jev or {}
    draft = draft or {}
    second_reads = second_reads or []

    verdict = _answer(jev, "verdict")
    blocker = _answer(jev, "merge_blocker")
    choice = verdict.get("choice")
    confidence = verdict.get("confidence")
    blocker_noul = blocker.get("noul")

    if not jev or not verdict:
        reasons.append("Jev did not return a verdict.")
    if choice == "block":
        reasons.append("Jev's verdict is block.")
    if isinstance(blocker_noul, (int, float)) and blocker_noul >= MERGE_BLOCKER_DANGER:
        reasons.append(f"Jev's merge-blocker is {blocker_noul:.0%}, at or over {MERGE_BLOCKER_DANGER:.0%}.")
    if isinstance(confidence, (int, float)) and confidence < CONFIDENCE_FLOOR:
        reasons.append(f"Jev's verdict confidence is {confidence:.0%}, under {CONFIDENCE_FLOOR:.0%}.")

    cited = [path for path in (draft.get("paths") or []) if path]
    missing = [path for path in cited if path not in known_paths]
    if missing:
        reasons.append("The draft names paths that are not in this repository: " + ", ".join(missing[:5]) + ".")

    draft_safe = bool(draft.get("safe"))
    for read in second_reads:
        source = read.get("source") or "second reader"
        if read.get("error"):
            reasons.append(f"{source} did not answer ({read['error']}).")
            continue
        if draft_safe and read.get("safe") is False:
            reasons.append(f"{source} does not agree that this is safe.")
        for path in read.get("paths") or []:
            if path and path not in known_paths:
                reasons.append(f"{source} names a path that is not in the repository: {path}.")

    if second_reads_required and not second_reads:
        reasons.append("A second reader was required and none ran.")

    cleared = not reasons
    summary = (draft.get("summary") or "").strip() or "I do not have a written review yet."
    if cleared:
        tone = "ok"
        say = summary
    else:
        tone = "warn" if choice != "block" else "danger"
        if choice == "block" or (isinstance(blocker_noul, (int, float)) and blocker_noul >= MERGE_BLOCKER_DANGER):
            tone = "danger"
        say = "I am not calling this safe. " + " ".join(reasons) + " " + summary
    return {
        "cleared": cleared,
        "tone": tone,
        "say": say.strip(),
        "reasons": reasons,
        "verdict": choice,
        "confidence": confidence,
        "merge_blocker": blocker_noul,
    }
