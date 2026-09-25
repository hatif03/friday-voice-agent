"""Local checks that do not call AssemblyAI, Jev, or GitHub."""
from github_tools import confirm_write, create_issue, pending_write, set_turn_context
import map_pipeline
import review_gate


def test_imports_and_landmarks():
    blobs = {
        "src/app.py": b"from src.util import helper\n\n" + b"print(1)\n" * 50,
        "src/util.py": b"def helper():\n    return 1\n",
        "src/index.js": b"import { helper } from './util.js';\nexport const n = 1;\n",
        "src/util.js": b"export function helper(){ return 1 }\n",
        "README.md": b"# Hello\n",
    }
    fingerprint = map_pipeline.parse_files(blobs)
    assert "src/util.py" in fingerprint["files"]["src/app.py"]["imports"]
    assert "src/util.js" in fingerprint["files"]["src/index.js"]["imports"]
    assert fingerprint["files"]["src/index.js"]["landmark"]["entry"]
    assert fingerprint["files"]["src/app.py"]["landmark"]["hotspot"] or fingerprint["files"]["src/app.py"]["loc"] >= 40


def test_gate_blocks_false_safe():
    jev = {"answers": {"verdict": {"choice": "block", "confidence": 0.9}, "merge_blocker": {"noul": 0.2}}}
    draft = {"summary": "This looks fine to merge.", "safe": True, "paths": ["src/app.py"]}
    gate = review_gate.validate_review(jev=jev, draft=draft, known_paths={"src/app.py"}, second_reads=[])
    assert gate["cleared"] is False
    assert "not calling this safe" in gate["say"]
    assert "block" in gate["say"]


def test_gate_disagreement():
    jev = {
        "answers": {
            "verdict": {"choice": "approve_with_nits", "confidence": 0.8},
            "merge_blocker": {"noul": 0.1},
        }
    }
    draft = {"summary": "Narrow change.", "safe": True, "paths": ["src/app.py"]}
    second = [{"source": "k2", "safe": False, "paths": ["src/app.py"], "summary": "Race in the writer."}]
    gate = review_gate.validate_review(
        jev=jev, draft=draft, known_paths={"src/app.py"}, second_reads=second, second_reads_required=True,
    )
    assert gate["cleared"] is False
    assert "k2" in gate["say"]


def test_write_needs_a_later_yes():
    set_turn_context("turn-1", "please open an issue")
    staged = create_issue("Check the parser", "It drops imports.")
    assert staged["status"] == "pending_confirmation"
    same = confirm_write(confirmed=True, transcript_id="turn-1", user_transcript="yes")
    assert same["status"] == "waiting"
    assert pending_write() is not None
    rejected = confirm_write(confirmed=True, transcript_id="turn-2", user_transcript="not yet")
    assert rejected["status"] == "not_confirmed"
    assert pending_write() is not None


def test_every_voice_tool_returns_say():
    """Each of the 20 tools answers from its handler. No network."""
    import history
    import jev_gate
    import map_pipeline
    import specialists
    from github_tools import (
        add_comment,
        confirm_write,
        create_issue,
        get_commit_diff,
        list_open_issues,
        list_pull_requests,
        list_recent_commits,
        pending_write,
        set_active_repo,
    )

    payload = {
        "owner": "acme",
        "repo": "demo",
        "slug": "acme/demo",
        "branch": "main",
        "readme_path": None,
        "files": {
            "src/app.py": {
                "path": "src/app.py",
                "loc": 10,
                "kind": "source",
                "size": 80,
                "language": "py",
                "imports": [],
                "imported_by": [],
                "landmark": {"entry": True, "core": False, "hotspot": False},
            }
        },
        "landmarks": [{"path": "src/app.py", "loc": 10, "entry": True, "core": False, "hotspot": False}],
        "edges": [],
        "stats": {"files": 1, "loc": 10, "edges": 0, "folders": 1, "truncated": False, "languages": []},
        "keyterms": ["app"],
        "source_text": {"src/app.py": "print(1)\n"},
    }
    map_pipeline._cache["acme/demo@default"] = payload
    map_pipeline.open_repo = lambda slug: payload
    set_active_repo("acme/demo")
    jev_gate.choose_landmark = lambda paths: {"answers": {}}
    jev_gate.review_change = lambda title, body, diff: {
        "answers": {"verdict": {"choice": "approve_with_nits", "confidence": 0.9}, "merge_blocker": {"noul": 0.1}}
    }
    jev_gate.needs_second_reader = lambda review: False
    specialists.gateway_draft = lambda evidence: {
        "summary": "Narrow change.",
        "safe": True,
        "paths": ["src/app.py"],
        "source": "llm_gateway",
    }
    specialists.gateway_graph = lambda listing, readme: {
        "summary": "One module.",
        "nodes": [{"id": "app", "path": "src/app.py", "label": "app"}],
        "edges": [],
        "groups": [],
    }
    specialists.vertex_read = lambda evidence: {"safe": True, "summary": "Agreed.", "paths": ["src/app.py"]}
    import github_tools

    github_tools.list_recent_commits = lambda count=20: {
        "commits": [{"sha": "abc", "message": "init", "author": "ada", "files": ["src/app.py"]}],
        "say": "Latest commit: init",
    }
    github_tools.list_open_issues = lambda: {"issues": [{"number": 1, "title": "Parser"}], "say": "1 open issues."}
    github_tools.list_pull_requests = lambda: {"pulls": [], "say": "No open pull requests."}
    github_tools.get_commit_diff = lambda sha: {
        "message": "init",
        "files": [{"filename": "src/app.py", "patch": "@@\n+print(1)"}],
    }
    import orchestrator

    orchestrator.list_recent_commits = github_tools.list_recent_commits
    orchestrator.get_commit_diff = github_tools.get_commit_diff
    orchestrator.list_open_issues = github_tools.list_open_issues
    orchestrator.list_pull_requests = github_tools.list_pull_requests
    history.load_window = lambda count=30: {
        "say": "3 commits from ada.",
        "commits": [{"author": "ada", "date": "2026-01-01", "message": "init", "files": ["src/app.py"], "short": "abc"}],
        "contributors": 1,
    }
    history.who_touched = lambda path: {"say": "ada wrote this.", "authors": [{"name": "ada", "count": 1}]}
    history.explain_fix = lambda query: {"say": "Pull 4 closed issue 12.", "issue": 12, "pull": 4}
    history.read_thread = lambda kind, number: {"say": "One comment on the issue.", "title": "Parser", "thread": []}
    history.scan_noise = lambda: {"say": "No repeated issues.", "candidates": []}
    import security

    security.scan_open = lambda: {"say": "Nothing in the files on screen matched the checks.", "findings": [], "paths": []}
    import ask

    ask.answer = lambda question: {"say": "It prints 1.", "paths": ["src/app.py"], "steps": [{"step": "files", "detail": "src/app.py"}]}

    calls = {
        "open_repository": {"repo": "acme/demo"},
        "describe_map": {},
        "focus_file": {"path": "src/app.py"},
        "list_landmarks": {},
        "set_map_layer": {"layer": "heat", "enabled": True},
        "review_changes": {},
        "explain_architecture": {},
        "list_recent_commits": {"count": 1},
        "list_open_issues": {},
        "list_pull_requests": {},
        "scrub_history": {"count": 5},
        "who_touched": {"path": "src/app.py"},
        "explain_fix": {"query": "12"},
        "read_thread": {"kind": "issue", "number": 1},
        "scan_noise": {},
        "scan_security": {},
        "ask_repository": {"question": "What does app do?"},
        "create_issue": {"title": "Check the parser", "body": "It drops imports."},
    }
    assert set(calls) | {"add_comment", "confirm_write"} == set(orchestrator._HANDLERS)
    for name, arguments in calls.items():
        outcome = orchestrator.dispatch(name, arguments, "look at the repo", "turn-tools")
        assert outcome.get("say"), name
        assert "is_error" not in outcome or outcome["is_error"] is False, name
    missed = orchestrator.dispatch("focus_file", {"path": "no/such.py"}, "", "turn-tools")
    assert missed["is_error"] is True
    assert "can't see" in missed["say"]
    unknown = orchestrator.dispatch("not_a_tool", {}, "", "turn-tools")
    assert unknown["is_error"] is True
    staged = orchestrator.dispatch(
        "create_issue",
        {"title": "Check the parser", "body": "It drops imports."},
        "please open an issue",
        "turn-same",
    )
    assert staged["result"]["status"] == "pending_confirmation"
    same = orchestrator.dispatch("confirm_write", {"confirmed": True}, "yes", "turn-same")
    assert same["result"]["status"] == "waiting"
    assert pending_write() is not None
    assert create_issue and add_comment and confirm_write and list_recent_commits and list_open_issues and list_pull_requests and get_commit_diff


if __name__ == "__main__":
    test_imports_and_landmarks()
    test_gate_blocks_false_safe()
    test_gate_disagreement()
    test_write_needs_a_later_yes()
    test_every_voice_tool_returns_say()
    print("ok")
