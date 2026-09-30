"""Deterministic checks plus OSV advisories, scored by Jev.

Scope is the files already in the map. Nothing here edits or closes a finding.
"""
import json
import re

import requests

from github_tools import active_repo
import jev_gate
import map_pipeline

SECRET = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}"
)
AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")
RISKY = re.compile(
    r"\beval\s*\(|\bexec\s*\(|pickle\.loads\s*\(|yaml\.load\s*\(|dangerouslySetInnerHTML|innerHTML\s*="
)
LICENSE_NAMES = {"license", "license.md", "license.txt", "copying", "copying.md", "unlicense"}
FLOOR = 0.9


def scan_open() -> dict:
    payload = map_pipeline.get_cached(active_repo())
    if not payload:
        raise RuntimeError("No repository is open.")
    findings = _deterministic(payload)
    findings.extend(_advisories(payload))
    _score(findings)
    cleared = [
        item
        for item in findings
        if isinstance(item.get("noul"), (int, float)) and item["noul"] >= FLOOR
    ]
    if cleared:
        bits = [f"{item['kind']} in {item['path'] or 'the repository'}" for item in cleared[:4]]
        say = "Worth a look: " + "; ".join(bits) + "."
    elif findings:
        say = "I have candidates on the map. None cleared the confidence floor, so I am not calling them confirmed."
    else:
        say = "Nothing in the files on screen matched the checks."
    try:
        import store

        store.record_scan(payload["slug"], say, findings)
    except Exception:
        pass
    public = [
        {
            "path": item.get("path") or "",
            "kind": item.get("kind") or "",
            "title": item.get("title") or "",
            "noul": item.get("noul"),
        }
        for item in findings
    ]
    return {
        "say": say,
        "findings": public,
        "paths": [item["path"] for item in public if item["path"] and item["path"] in payload["files"]],
    }


def _deterministic(payload: dict) -> list:
    texts = payload.get("source_text") or {}
    found = []
    names = {path.split("/")[-1].lower() for path in payload["files"]}
    if not names.intersection(LICENSE_NAMES):
        found.append(
            {
                "path": "",
                "kind": "license",
                "title": "No license file is in the map.",
                "evidence": "Expected LICENSE, COPYING, or UNLICENSE.",
            }
        )
    for path, text in texts.items():
        if SECRET.search(text) or AWS_KEY.search(text) or PRIVATE_KEY.search(text):
            found.append(
                {
                    "path": path,
                    "kind": "secret",
                    "title": "Possible secret in this file.",
                    "evidence": path,
                }
            )
        if RISKY.search(text):
            found.append(
                {
                    "path": path,
                    "kind": "risky_call",
                    "title": "Risky call in this file.",
                    "evidence": path,
                }
            )
        if len(found) >= 24:
            break
    return found


def _advisories(payload: dict) -> list:
    raw = (payload.get("source_text") or {}).get("package.json")
    if not raw:
        for path, text in (payload.get("source_text") or {}).items():
            if path.endswith("package.json"):
                raw = text
                break
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    names = list((data.get("dependencies") or {}).keys())[:30]
    if not names:
        return []
    try:
        response = requests.post(
            "https://api.osv.dev/v1/querybatch",
            json={"queries": [{"package": {"ecosystem": "npm", "name": name}} for name in names]},
            timeout=12,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except requests.RequestException:
        return []
    found = []
    for name, result in zip(names, results):
        vulns = result.get("vulns") or []
        if not vulns:
            continue
        found.append(
            {
                "path": "package.json",
                "kind": "advisory",
                "title": f"{name} has an OSV advisory.",
                "evidence": str(vulns[0].get("id") or name),
            }
        )
        if len(found) >= 8:
            break
    return found


def _score(findings: list) -> None:
    for item in findings[:5]:
        try:
            scored = jev_gate.finding_noul(item["title"], item.get("evidence") or item["title"])
            noul = ((scored.get("answers") or {}).get("real_issue") or {}).get("noul")
            if isinstance(noul, (int, float)):
                item["noul"] = float(noul)
        except Exception:
            item["noul"] = None
