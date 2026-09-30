"""One check every review has to clear before Friday may sound sure.

Jev owns a confident verdict. When Jev is unsure, the escalated reader owns
the decision. AssemblyAI phrases that decision and does not vote. A missing
escalated reader is not a softer bar.
"""
from __future__ import annotations

from jev_gate import ACCEPT_AT

MERGE_BLOCKER_DANGER = 0.65


def _answer(jev: dict, key: str) -> dict:
    return ((jev or {}).get("answers") or {}).get(key) or {}


def _invented(paths: list, known_paths: set[str], source: str) -> list[str]:
    missing = [path for path in paths if path and path not in known_paths]
    if not missing:
        return []
    return [f"{source} names a path that is not in the repository: {', '.join(missing[:5])}."]


def validate_review(
    *,
    jev: dict | None,
    draft: dict | None,
    known_paths: set[str],
    route: str = "accept",
    reader: dict | None = None,
) -> dict:
    """Return cleared, tone, say, and the reasons a human can inspect."""
    reasons: list[str] = []
    jev = jev or {}
    draft = draft or {}
    verdict = _answer(jev, "verdict")
    blocker = _answer(jev, "merge_blocker")
    choice = verdict.get("choice")
    confidence = verdict.get("confidence")
    blocker_noul = blocker.get("noul")
    decided_by = "jev" if route == "accept" else (reader or {}).get("source") or "reader"

    reasons.extend(_invented(draft.get("paths") or [], known_paths, "The draft"))
    if route == "accept":
        if not choice:
            reasons.append("Jev did not return a verdict.")
        if not isinstance(confidence, (int, float)) or confidence < ACCEPT_AT:
            reasons.append(f"Jev's verdict confidence is under {ACCEPT_AT:.0%}.")
        if choice == "block":
            reasons.append("Jev's verdict is block.")
        elif choice == "request_changes":
            reasons.append("Jev's verdict is request changes.")
        elif choice != "approve_with_nits":
            reasons.append("Jev did not approve this change.")
        if not isinstance(blocker_noul, (int, float)) or blocker_noul >= MERGE_BLOCKER_DANGER:
            if isinstance(blocker_noul, (int, float)) and blocker_noul >= MERGE_BLOCKER_DANGER:
                reasons.append(
                    f"Jev's merge-blocker is {blocker_noul:.0%}, at or over {MERGE_BLOCKER_DANGER:.0%}."
                )
            else:
                reasons.append("Jev's merge-blocker is not under the danger line.")
    else:
        if not reader or reader.get("error"):
            detail = (reader or {}).get("error") or "none ran"
            reasons.append(f"A second reader was required and did not answer ({detail}).")
        else:
            source = reader.get("source") or "second reader"
            if reader.get("safe") is not True:
                reasons.append(f"{source} is not calling this safe.")
            reasons.extend(_invented(reader.get("paths") or [], known_paths, source))

    cleared = not reasons
    summary = (draft.get("summary") or "").strip()
    if not summary and route == "escalate" and reader:
        summary = (reader.get("summary") or "").strip()
    if not summary:
        summary = "I do not have a written review yet."
    if cleared:
        tone = "ok"
        say = summary
    else:
        tone = "danger" if choice == "block" or (
            isinstance(blocker_noul, (int, float)) and blocker_noul >= MERGE_BLOCKER_DANGER
        ) else "warn"
        say = "I am not calling this safe. " + " ".join(reasons) + " " + summary
    return {
        "cleared": cleared,
        "tone": tone,
        "say": say.strip(),
        "reasons": reasons,
        "verdict": choice,
        "confidence": confidence,
        "merge_blocker": blocker_noul,
        "route": route,
        "decided_by": decided_by,
    }
