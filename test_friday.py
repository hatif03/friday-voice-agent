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
    jev = {"answers": {"verdict": {"choice": "block", "confidence": 0.95}, "merge_blocker": {"noul": 0.2}}}
    draft = {"summary": "This looks fine to merge.", "paths": ["src/app.py"]}
    gate = review_gate.validate_review(jev=jev, draft=draft, known_paths={"src/app.py"}, route="accept")
    assert gate["cleared"] is False
    assert gate["decided_by"] == "jev"
    assert "not calling this safe" in gate["say"]
    assert "block" in gate["say"]


def test_confident_approve_clears_without_a_reader():
    jev = {
        "answers": {
            "verdict": {"choice": "approve_with_nits", "confidence": 0.93},
            "merge_blocker": {"noul": 0.2},
        }
    }
    draft = {"summary": "Narrow change.", "paths": ["src/app.py"]}
    gate = review_gate.validate_review(jev=jev, draft=draft, known_paths={"src/app.py"}, route="accept", reader=None)
    assert gate["cleared"] is True
    assert gate["route"] == "accept"
    assert gate["say"] == "Narrow change."


def test_unsure_verdict_needs_a_reader():
    jev = {
        "answers": {
            "verdict": {"choice": "approve_with_nits", "confidence": 0.4},
            "merge_blocker": {"noul": 0.1},
        }
    }
    draft = {"summary": "Narrow change.", "paths": ["src/app.py"]}
    missing = review_gate.validate_review(jev=jev, draft=draft, known_paths={"src/app.py"}, route="escalate")
    assert missing["cleared"] is False
    assert "second reader" in missing["say"]
    reader = {"source": "vertex", "safe": True, "paths": ["src/app.py"], "summary": "The change is local."}
    cleared = review_gate.validate_review(
        jev=jev, draft=draft, known_paths={"src/app.py"}, route="escalate", reader=reader,
    )
    assert cleared["cleared"] is True
    assert cleared["decided_by"] == "vertex"
    refused = review_gate.validate_review(
        jev=jev,
        draft=draft,
        known_paths={"src/app.py"},
        route="escalate",
        reader={"source": "k2", "safe": False, "paths": ["src/app.py"], "summary": "Race in the writer."},
    )
    assert refused["cleared"] is False
    assert "k2" in refused["say"]


def test_sign_in_restores_and_answers_link_out():
    import os
    import tempfile

    import github_tools

    saved_path = github_tools._SESSION_PATH
    saved_token = os.environ.get("GITHUB_TOKEN")
    saved_login = github_tools._session_login
    saved_file = github_tools._file_token
    folder = tempfile.mkdtemp()
    github_tools._SESSION_PATH = os.path.join(folder, "session")
    try:
        assert github_tools.safe_return_path("https://evil.example") == "/"
        assert github_tools.safe_return_path("/?repo=acme%2Fdemo") == "/?repo=acme%2Fdemo"
        github_tools._save_session("token-test", "hatif03")
        os.environ["GITHUB_TOKEN"] = ""
        github_tools._session_login = None
        github_tools._file_token = ""
        github_tools._load_session()
        assert os.environ.get("GITHUB_TOKEN") == "token-test"
        assert github_tools._session_login == "hatif03"
    finally:
        github_tools._clear_session()
        github_tools._SESSION_PATH = saved_path
        github_tools._session_login = saved_login
        github_tools._file_token = saved_file
        if saved_token is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = saved_token
        os.rmdir(folder)


def test_confirm_without_github_keeps_the_draft():
    import os

    import github_tools

    saved = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = ""
    github_tools._pending = None
    try:
        github_tools.set_turn_context("draft", "open an issue")
        staged = github_tools.create_issue("Friday test", "")
        assert staged["status"] == "pending_confirmation"
        result = github_tools.confirm_write(confirmed=True, transcript_id="later", user_transcript="Yes.")
        assert result["status"] == "needs_github"
        assert result["say"] == "The draft is still waiting. Connect GitHub, then say yes again."
        assert "GITHUB_TOKEN" not in result["say"]
        assert github_tools.pending_write()["payload"]["title"] == "Friday test"
    finally:
        github_tools._pending = None
        if saved is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = saved


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
    specialists.gateway_phrase = lambda evidence: {
        "summary": "Narrow change.",
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

    original_answer = ask.answer
    original_explain = ask.explain_source
    original_landmarks = ask.explain_landmarks
    original_repo = ask.explain_repository
    ask.answer = lambda question: {"say": "It prints 1.", "paths": ["src/app.py"], "steps": [{"step": "files", "detail": "src/app.py"}]}
    ask.explain_source = lambda path, text: "It prints one."
    ask.explain_landmarks = lambda payload: [
        {"path": "src/app.py", "sentence": "It prints one."}
    ]
    ask.explain_repository = lambda question, payload, history=None: {
        "say": "### Analysis\n\n- **Purpose**: a demo.",
        "spoken": "This is a demo.",
        "paths": ["README.md"],
    }
    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "describe_map", "confidence": 0.95}}}
    specialists.k2_choose_tool = lambda evidence, names: (_ for _ in ()).throw(AssertionError("k2"))

    calls = {
        "open_repository": {"repo": "acme/demo"},
        "describe_map": {},
        "focus_file": {"path": "src/app.py"},
        "list_landmarks": {},
        "explain_landmarks": {},
        "set_map_layer": {"layer": "heat", "enabled": True},
        "review_changes": {},
        "latest_change": {},
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
        "explain_project": {},
        "explain_file": {"path": "src/app.py"},
        "give_up": {},
        "friday_turn": {"utterance": "What is open?"},
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
    ask.answer = original_answer
    ask.explain_source = original_explain
    ask.explain_landmarks = original_landmarks
    ask.explain_repository = original_repo


def test_confident_block_skips_readers():
    import jev_gate
    import specialists
    import orchestrator

    called = []
    jev_gate.review_change = lambda title, body, diff: {
        "answers": {"verdict": {"choice": "block", "confidence": 0.96}, "merge_blocker": {"noul": 0.1}}
    }
    specialists.vertex_read = lambda evidence: called.append("vertex")
    specialists.k2_read = lambda evidence: called.append("k2")
    specialists.gateway_phrase = lambda evidence: {"summary": "This looks fine to merge.", "paths": ["src/app.py"]}
    judged = orchestrator.judge_change("init", "", "FILE src/app.py\n+print(1)", ["src/app.py"], {"src/app.py"})
    assert called == []
    assert judged["route"] == "accept"
    assert judged["decided_by"] == "jev"
    assert judged["gate"]["cleared"] is False


def test_gemini_error_falls_through_to_k2():
    import jev_gate
    import specialists
    import orchestrator

    called = []
    jev_gate.review_change = lambda title, body, diff: {
        "answers": {"verdict": {"choice": "approve_with_nits", "confidence": 0.4}, "merge_blocker": {"noul": 0.1}}
    }

    def vertex(evidence):
        called.append("vertex")
        return {"source": "vertex", "error": "Vertex down", "safe": False, "paths": []}

    def k2(evidence):
        called.append("k2")
        return {"source": "k2", "safe": True, "summary": "The change is local.", "paths": ["src/app.py"], "concerns": []}

    specialists.vertex_read = vertex
    specialists.k2_read = k2
    specialists.gateway_phrase = lambda evidence: {"summary": "The change is local.", "paths": ["src/app.py"]}
    judged = orchestrator.judge_change("init", "", "FILE src/app.py\n+print(1)", ["src/app.py"], {"src/app.py"})
    assert called == ["vertex", "k2"]
    assert judged["route"] == "escalate"
    assert judged["decided_by"] == "k2"
    assert judged["gate"]["cleared"] is True
    assert jev_gate.route({"answers": {"verdict": {"confidence": 0.89}}}) == "escalate"
    assert jev_gate.route({"answers": {}}) == "escalate"
    assert jev_gate.route({"answers": {"verdict": {"confidence": 0.9}}}) == "accept"


def test_voice_prompt_names_the_open_repo():
    import github_tools
    import voice_broker

    github_tools.set_active_repo("hatif03/pocketless")
    prompt = voice_broker.system_prompt()
    assert "hatif03/pocketless" in prompt
    assert "hatif03" in voice_broker.repo_keyterms()
    assert "pocketless" in voice_broker.repo_keyterms()
    greeting = voice_broker.spoken_greeting()
    assert greeting.startswith("pocketless is open")
    assert "hatif03" in greeting


def test_map_question_describes_the_fingerprint():
    import ask
    import github_tools
    import map_pipeline

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "slug": "acme/demo",
        "files": {"src/app.py": {}},
        "landmarks": [{"path": "src/app.py"}],
        "stats": {"files": 172, "loc": 100, "edges": 14, "truncated": False},
    }
    result = ask.answer("Explain this map to me")
    assert "acme/demo" in result["say"]
    assert "Bigger circles" in result["say"]
    assert "snippets" not in result["say"].lower()


def test_landmarks_and_largest_file_are_grounded():
    import ask
    import github_tools
    import map_pipeline

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "slug": "acme/demo",
        "files": {
            "src/small.py": {"loc": 10, "imports": [], "imported_by": []},
            "src/big.py": {"loc": 400, "imports": [], "imported_by": []},
        },
        "landmarks": [
            {"path": "src/big.py", "loc": 400, "entry": True, "core": False, "hotspot": True},
        ],
        "source_text": {"src/big.py": "def plan_trip():\n    return 1\n"},
        "stats": {"files": 2, "loc": 410, "edges": 0, "truncated": False},
    }
    landmarks = ask.answer("What are the landmarks in this repository?")
    assert "src/big.py" in landmarks["say"]
    assert "400 lines" in landmarks["say"]
    largest = ask.answer("What is the largest file in this repository?")
    assert largest["say"].startswith("The largest file is src/big.py, 400 lines.")
    assert "plan_trip" in largest["say"]
    assert largest["paths"] == ["src/big.py"]


def test_ask_runs_the_tool_the_model_calls():
    import chat
    import github_tools
    import jev_gate
    import map_pipeline
    import orchestrator
    import specialists

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "give_up", "confidence": 0.4}}}
    seen = {}

    def fake_k2(evidence, names):
        seen["names"] = list(names)
        return {"tool": "list_open_issues"}

    specialists.k2_choose_tool = fake_k2
    original = orchestrator._HANDLERS["list_open_issues"]
    orchestrator._HANDLERS["list_open_issues"] = lambda arguments, transcript: {
        "say": "Read from GitHub.",
        "ui_commands": [],
        "trace": [{"step": "tool", "name": "list_open_issues"}],
        "result": {"say": "Read from GitHub."},
    }
    try:
        result = chat.turn("What's waiting on the tracker?")
    finally:
        orchestrator._HANDLERS["list_open_issues"] = original
    assert "list_open_issues" in seen["names"]
    assert "explain_file" in seen["names"]
    assert result["say"] == "Read from GitHub."
    assert result["steps"][0]["step"] == "k2"
    assert result["steps"][0]["detail"] == "list_open_issues"


def test_tool_error_does_not_quote_files():
    import ask
    import github_tools
    import map_pipeline

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "slug": "acme/demo",
        "files": {"src/app.py": {"loc": 3, "imports": [], "imported_by": []}},
        "landmarks": [],
        "source_text": {"src/app.py": "def share_view():\n    return 1\n"},
        "stats": {"files": 1, "loc": 3, "edges": 0, "truncated": False},
    }

    def fake_gateway(messages, tools=None):
        assert tools
        return ask._GatewayMessage(error="model does not support tools")

    ask._gateway = fake_gateway
    result = ask.answer("Are there any open issues in this repository?")
    assert result["say"] == "I could not call a tool for that."
    assert "share_view" not in result["say"]
    assert "closest files" not in result["say"].lower()


def _demo_map():
    return {
        "slug": "acme/demo",
        "files": {
            "src/app.py": {
                "loc": 12,
                "kind": "code",
                "landmark": {"entry": True, "core": False, "hotspot": False},
                "imported_by": [],
                "imports": [],
            }
        },
        "landmarks": [{"path": "src/app.py", "entry": True, "core": False, "hotspot": False, "loc": 12}],
        "source_text": {"src/app.py": "def plan_trip():\n    return 1\n"},
        "stats": {"files": 1, "loc": 12, "edges": 0, "truncated": False},
    }


def test_turn_explains_the_focused_file_without_k2():
    import ask
    import chat
    import github_tools
    import jev_gate
    import map_pipeline
    import specialists

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    chat.note_focus("src/app.py")
    seen = []
    jev_gate.choose_tool = lambda state: seen.append(state) or {
        "answers": {"tool": {"choice": "explain_file", "confidence": 0.95}}
    }
    specialists.k2_choose_tool = lambda evidence, names: (_ for _ in ()).throw(AssertionError("k2"))
    ask.explain_source = lambda path, text: "It plans a trip."
    result = chat.turn("What does this file do?")
    assert "Focused file: src/app.py" in seen[0]
    assert result["steps"][0]["step"] == "jev"
    assert result["steps"][0]["detail"] == "explain_file"
    assert "src/app.py" in result["say"]
    assert "plans a trip" in result["say"]
    assert "kind" not in result["say"]
    jev_gate.choose_tool = lambda state: seen.append(state) or {
        "answers": {"tool": {"choice": "give_up", "confidence": 0.95}}
    }
    chat.turn("Thanks")
    assert "What does this file do?" in seen[-1]


def test_focus_does_not_explain_and_a_purpose_question_does():
    import ask
    import chat
    import github_tools
    import jev_gate
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    chat.note_focus("src/app.py")
    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "focus_file", "confidence": 0.95}}}
    ask.explain_source = lambda path, text: (_ for _ in ()).throw(AssertionError("explain"))
    focused = chat.turn("Focus on src/app.py")
    assert "12 lines" in focused["say"]
    assert "plan_trip" not in focused["say"]
    ask.explain_source = lambda path, text: "It plans a trip."
    explained = chat.turn("What does this file do?")
    assert "plans a trip" in explained["say"]
    assert explained["steps"][0]["detail"] == "explain_file"


def test_explain_project_reads_the_readme():
    import ask
    import chat
    import github_tools
    import jev_gate
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    payload = _demo_map()
    payload["files"]["README.md"] = {
        "loc": 2,
        "kind": "doc",
        "landmark": {"entry": False, "core": False, "hotspot": False},
        "imported_by": [],
        "imports": [],
    }
    payload["source_text"]["README.md"] = "# Midnight Pool\nRoutes cross-chain liquidity.\n"
    map_pipeline._cache["acme/demo@default"] = payload
    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "explain_file", "confidence": 0.95}}}
    seen = {}

    def fake(question, body, history=None):
        seen["paths"] = ask.select_files(question, body)
        return {
            "say": "### Analysis\n\n- **Purpose**: routes liquidity.",
            "spoken": "Midnight Pool routes cross-chain liquidity.",
            "paths": seen["paths"],
        }

    original = ask.explain_repository
    ask.explain_repository = fake
    result = chat.turn("Explain this project to me.")
    ask.explain_repository = original
    assert "README.md" in seen["paths"]
    assert "can't find that file" not in result["say"]
    assert result["steps"][0]["detail"] == "explain_project"
    assert "liquidity" in result["spoken"]


def test_production_scenarios():
    """The questions a person actually asks, plus the nearby cases those imply."""
    import ask
    import chat
    import github_tools
    import history
    import jev_gate
    import map_pipeline
    import orchestrator
    import specialists

    linked = orchestrator._plain(
        "list_open_issues",
        {"issues": [{"number": 9, "title": "Pool fee", "url": "https://github.com/acme/demo/issues/9"}]},
    )
    assert "https://github.com/acme/demo/issues/9" in linked

    chat.reset()
    github_tools._pending = None
    github_tools.set_active_repo("hatif03/demo")
    payload = {
        "owner": "hatif03",
        "repo": "demo",
        "slug": "hatif03/demo",
        "files": {
            "src/main.py": {
                "loc": 20,
                "kind": "code",
                "landmark": {"entry": True, "core": False, "hotspot": False},
                "imported_by": [],
                "imports": ["src/big.py"],
            },
            "src/big.py": {
                "loc": 400,
                "kind": "code",
                "landmark": {"entry": False, "core": False, "hotspot": True},
                "imported_by": ["src/main.py"],
                "imports": [],
            },
            "README.md": {
                "loc": 8,
                "kind": "doc",
                "landmark": {"entry": False, "core": False, "hotspot": False},
                "imported_by": [],
                "imports": [],
            },
        },
        "landmarks": [
            {"path": "src/main.py", "loc": 20, "entry": True, "core": False, "hotspot": False},
            {"path": "src/big.py", "loc": 400, "entry": False, "core": True, "hotspot": True},
        ],
        "source_text": {
            "README.md": "# Demo\nA cross-chain pool.\n",
            "src/big.py": "def pool():\n    return 1\n",
            "src/main.py": "import pool\n",
        },
        "stats": {"files": 3, "loc": 428, "edges": 1, "truncated": False},
    }
    map_pipeline._cache["hatif03/demo@default"] = payload

    commits = [
        {"sha": "aaa111", "message": "open the pool"},
        {"sha": "bbb222", "message": "add the fee"},
        {"sha": "ccc333", "message": "wire the bridge"},
        {"sha": "ddd444", "message": "document the map"},
        {"sha": "eee555", "message": "fix the quote"},
    ]

    def commits_fn(count=5):
        return {"commits": commits[:count]}

    def diff_fn(sha):
        return {"sha": sha, "message": "open the pool", "files": [{"filename": "src/big.py", "patch": "+pool"}]}

    def issues_fn(count=10):
        return {"issues": [{"number": 9, "title": "Pool fee"}]}

    def pulls_fn(count=5):
        return {"pulls": []}

    commits_fn.__name__ = "list_recent_commits"
    issues_fn.__name__ = "list_open_issues"
    pulls_fn.__name__ = "list_pull_requests"

    orchestrator.list_recent_commits = commits_fn
    orchestrator.get_commit_diff = diff_fn
    orchestrator.list_open_issues = issues_fn
    orchestrator.list_pull_requests = pulls_fn
    orchestrator._HANDLERS["list_recent_commits"] = orchestrator._passthrough(commits_fn)
    orchestrator._HANDLERS["list_open_issues"] = orchestrator._passthrough(issues_fn)
    orchestrator._HANDLERS["list_pull_requests"] = orchestrator._passthrough(pulls_fn)
    history.who_touched = lambda path: {"say": f"ada wrote {path}.", "authors": [{"name": "ada", "count": 2}]}

    def read_thread(kind, number):
        if int(number) == 1:
            raise RuntimeError("GitHub API GET issue 1 failed (404)")
        return {"kind": "issue", "number": int(number), "title": "Pool fee", "thread": [{"body": "fee"}], "say": "Pool fee. 1 posts in the thread."}

    history.read_thread = read_thread
    history.scan_noise = lambda: {"say": "I don't see a burst of repeated issues in the open list.", "candidates": []}
    import security

    security.scan_open = lambda: {"say": "Nothing in the files on screen matched the checks.", "findings": [], "paths": []}
    ask.explain_source = lambda path, text: "It routes the pool."
    ask.explain_landmarks = lambda payload: [
        {"path": item["path"], "sentence": f"{item['path']} handles its part of the repo."}
        for item in (payload.get("landmarks") or [])[:12]
    ]
    specialists.gateway_graph = lambda listing, readme: {
        "summary": "The entry file calls the pool.",
        "nodes": [{"id": "main", "path": "src/main.py", "label": "main"}],
        "edges": [],
        "groups": [],
    }
    specialists.vertex_read = lambda evidence: {"error": "skipped", "safe": False, "paths": []}
    specialists.gateway_phrase = lambda evidence: {"summary": "Small change.", "paths": ["src/main.py"], "source": "llm_gateway"}
    jev_gate.review_change = lambda title, body, diff: {
        "answers": {"verdict": {"choice": "approve_with_nits", "confidence": 0.95}, "merge_blocker": {"noul": 0.1}}
    }
    jev_gate.choose_tool = lambda state: (_ for _ in ()).throw(AssertionError("jev should not choose a direct request"))
    specialists.k2_choose_tool = lambda evidence, names: (_ for _ in ()).throw(AssertionError("k2"))

    posted = []
    github_tools._require_token = lambda: None
    github_tools._request = lambda method, path, **kwargs: posted.append((method, path, kwargs.get("json"))) or {
        "number": 42,
        "html_url": "https://github.com/hatif03/demo/issues/42",
    }

    def ask_turn(text):
        return chat.turn(text)

    opened = ask_turn("What repository is open, and who owns it?")
    assert opened["say"].startswith("demo is open. hatif03 owns it.")
    assert "https://github.com/hatif03/demo" in opened["say"]
    assert opened["steps"][0]["detail"] == "name_open_repo"

    mapped = ask_turn("Explain this map to me.")
    assert "Bigger circles" in mapped["say"]
    assert "https://github.com/hatif03/demo" in mapped["say"]
    assert "can't find that file" not in mapped["say"]
    assert mapped["steps"][0]["detail"] == "describe_map"

    landmarks = ask_turn("What are the landmarks?")
    assert "src/main.py" in landmarks["say"] and "src/big.py" in landmarks["say"]
    assert landmarks["steps"][0]["detail"] == "list_landmarks"

    landmark_files = ask_turn("What are the landmark files in this repository?")
    assert landmark_files["steps"][0]["detail"] == "list_landmarks"
    assert "src/main.py" in landmark_files["say"]

    landmark_app = ask_turn("What are the landmark files in this application?")
    assert landmark_app["steps"][0]["detail"] == "list_landmarks"
    assert "src/main.py" in landmark_app["say"]

    explained = ask_turn("Explain each of those landmark files to me.")
    assert explained["steps"][0]["detail"] == "explain_landmarks"
    assert "handles its part of the repo" in explained["say"]
    assert "https://github.com/hatif03/demo" in explained["say"]
    assert not explained["say"].startswith("Landmarks:")

    entry = ask_turn("Focus the main entry file.")
    assert entry["ui_commands"][0] == {"type": "focus", "path": "src/main.py"}
    assert "entry" in entry["say"]

    author = ask_turn("Who wrote that file?")
    assert author["say"].startswith("ada wrote src/main.py.")
    assert "https://github.com/hatif03/demo" in author["say"]

    links = ask_turn("Show import links.")
    assert links["ui_commands"][0] == {"type": "layer", "layer": "edges", "enabled": True}
    sized = ask_turn("Size the circles by lines.")
    assert sized["ui_commands"][0] == {"type": "layer", "layer": "loc", "enabled": True}
    hidden = ask_turn("Hide the heat layer.")
    assert hidden["ui_commands"][0] == {"type": "layer", "layer": "heat", "enabled": False}
    shown = ask_turn("Show the heat layer.")
    assert shown["ui_commands"][0] == {"type": "layer", "layer": "heat", "enabled": True}

    largest = ask_turn("What does the largest file do?")
    assert largest["paths"] == ["src/big.py"]
    assert "routes the pool" in largest["say"]
    assert "can't find that file" not in largest["say"]

    start = ask_turn("Where does this program start?")
    assert "src/main.py" in start["say"]

    pieces = ask_turn("Explain how the pieces fit together.")
    assert "entry file calls the pool" in pieces["say"]
    assert pieces["steps"][0]["detail"] == "explain_architecture"

    changed = ask_turn("What changed in the latest commit?")
    assert "open the pool" in changed["say"] and "src/big.py" in changed["say"]

    recent = ask_turn("Read the last 5 commits.")
    for message in ("open the pool", "add the fee", "wire the bridge", "document the map", "fix the quote"):
        assert message in recent["say"]

    issues = ask_turn("Are there open issues?")
    assert "Pool fee" in issues["say"]
    pulls = ask_turn("Are there open pull requests?")
    assert "no open pull requests" in pulls["say"]

    review = ask_turn("Review the latest commit. Is it safe to merge?")
    assert review["say"].startswith("Small change.")
    assert "https://github.com/hatif03/demo/commit/aaa111" in review["say"]
    assert review["steps"][0]["detail"] == "review_changes"

    missing = ask_turn("Read issue 1. If there is no issue 1, ask for the newest open issue instead.")
    assert "not there" in missing["say"]
    assert "#9" in missing["say"]
    assert "Pool fee" in missing["say"]

    secure = ask_turn("Scan this repository for security issues.")
    assert "matched the checks" in secure["say"]
    assert "closed" not in secure["say"].lower()
    noise = ask_turn("Are there repeated or spam issues?")
    assert "did not close" in noise["say"] or "don't see a burst" in noise["say"]

    refused = ask_turn("Close issue 9.")
    assert refused["say"] == "I don't close issues or pull requests."
    assert posted == []

    plain = ask_turn("Open an issue titled Friday test for me.")
    assert plain["steps"][0]["detail"] == "create_issue"
    assert "have not posted" in plain["say"]
    assert "no open issues" not in plain["say"]
    assert github_tools.pending_write()["payload"]["title"] == "Friday test"
    github_tools.confirm_write(confirmed=False, transcript_id="clear-plain", user_transcript="no")

    named = ask_turn("I want you to open an issue for me named Friday test.")
    assert named["steps"][0]["detail"] == "create_issue"
    assert github_tools.pending_write()["payload"]["title"] == "Friday test"
    github_tools.confirm_write(confirmed=False, transcript_id="clear-named", user_transcript="no")

    same_breath = ask_turn('Open an issue titled "Friday test" that says this is a test. yes')
    assert "have not posted" in same_breath["say"]
    assert github_tools.pending_write()["payload"]["title"] == "Friday test"
    assert posted == []

    posted_turn = ask_turn("yes")
    assert posted_turn["say"].startswith("Posted issue 42.")
    assert posted[-1][0] == "POST"
    assert posted[-1][2]["title"] == "Friday test"
    assert github_tools.pending_write() is None

    ask_turn('Comment on issue 9 that the fee looks high')
    assert github_tools.pending_write()["kind"] == "comment"
    ask_turn("no")
    assert github_tools.pending_write() is None
    idle = ask_turn("yes")
    assert "nothing waiting" in idle["say"]
    assert len(posted) == 1

    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "give_up", "confidence": 0.95}}}
    weather = ask_turn("What is the weather on Mars?")
    assert weather["say"] == "I can't find that in this repository."
    assert weather["steps"][0]["step"] == "jev"

    try:
        chat.turn("")
        raise AssertionError("empty")
    except RuntimeError as exc:
        assert "Say something" in str(exc)
    github_tools.set_active_repo("missing/repo")
    try:
        chat.turn("What are the landmarks?")
        raise AssertionError("no map")
    except RuntimeError as exc:
        assert "No repository" in str(exc)


def test_github_gateway_routing():
    import chat
    import github_tools
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()

    assert chat._wants_github_gateway("Check the latest commits and tell me what changed.")
    assert not chat._wants_github_gateway("What are the landmarks?")
    assert not chat._wants_github_gateway("Explain each of those landmark files to me.")

    import agent

    original = agent.run_agent
    agent.run_agent = lambda utterance, transcript_id="": {
        "summary": "Checked commits. Nothing broken.",
        "tool_calls": [{"name": "list_recent_commits", "args": {}, "result": {}}],
    }
    try:
        result = chat.turn("Check the latest commits and tell me what changed.")
        assert result["steps"][0]["step"] == "gateway"
        assert "commits" in result["say"].lower()
    finally:
        agent.run_agent = original


def test_issue_title_followup_after_jev():
    import chat
    import github_tools
    import jev_gate
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()

    asked = chat.turn("If anything is broken, open an issue for it.")
    assert asked["say"] == "What should the issue be titled?"
    assert asked["steps"][0]["detail"] == "need_issue_title"

    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "create_issue", "confidence": 0.95}}}
    titled = chat.turn("Call it broken-in-stuff.")
    assert titled["steps"][0]["detail"] == "create_issue"
    assert "have not posted" in titled["say"]
    assert github_tools.pending_write()["payload"]["title"] == "broken-in-stuff"
    github_tools.confirm_write(confirmed=False, transcript_id="clear-title-follow", user_transcript="no")

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    chat.turn("Open an issue for me.")
    full = chat.turn("The title is Broken Issue and the body should be that code is broken.")
    assert full["steps"][0]["detail"] == "create_issue"
    pending = github_tools.pending_write()
    assert pending["payload"]["title"] == "Broken Issue"
    assert "broken" in pending["payload"]["body"].lower()
    github_tools.confirm_write(confirmed=False, transcript_id="clear-full", user_transcript="no")


def test_issue_comment_parsing_and_jev_fallback():
    import chat
    import github_tools
    import jev_gate
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    github_tools.note_posted_issue(2)

    titled = chat.turn("No, I want you to reply to the issue called first issue with a hello.")
    assert titled["steps"][0]["detail"] == "add_comment"
    assert "have not posted" in titled["say"]
    pending = github_tools.pending_write()
    assert pending["kind"] == "comment"
    assert pending["payload"]["body"] == "hello"
    github_tools.confirm_write(confirmed=False, transcript_id="clear-titled", user_transcript="no")

    numbered = chat.turn("The issue number is 2 and reply with a hello.")
    assert numbered["steps"][0]["detail"] == "add_comment"
    assert github_tools.pending_write()["payload"]["issue_number"] == 2
    github_tools.confirm_write(confirmed=False, transcript_id="clear-num", user_transcript="no")

    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "add_comment", "confidence": 0.95}}}
    via_jev = chat.turn("The issue number is 2 and reply with hello.")
    assert "have not posted" in via_jev["say"]
    assert github_tools.pending_write()["payload"]["issue_number"] == 2
    github_tools.confirm_write(confirmed=False, transcript_id="clear-jev", user_transcript="no")

    ask_body = chat.turn("Can you reply to the issue you just created?")
    assert ask_body["say"].startswith("What should I say on issue 2?")
    follow = chat.turn("hello")
    assert "have not posted" in follow["say"]
    assert github_tools.pending_write()["payload"]["body"] == "hello"
    github_tools.confirm_write(confirmed=False, transcript_id="clear-follow", user_transcript="no")


def test_give_up_is_honest():
    import chat
    import github_tools
    import jev_gate
    import map_pipeline

    chat.reset()
    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = _demo_map()
    jev_gate.choose_tool = lambda state: {"answers": {"tool": {"choice": "give_up", "confidence": 0.95}}}
    result = chat.turn("What is the weather on Mars?")
    assert result["say"] == "I can't find that in this repository."
    assert result["steps"][0] == {"step": "jev", "detail": "give_up", "confidence": 0.95}


def test_focus_command_can_call_focus_file():
    import ask
    import github_tools
    import map_pipeline

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "slug": "acme/demo",
        "files": {
            "src/main.py": {
                "loc": 12,
                "kind": "code",
                "landmark": {"entry": True, "core": False, "hotspot": False},
                "imported_by": [],
                "imports": [],
            }
        },
        "landmarks": [{"path": "src/main.py", "entry": True, "core": False, "hotspot": False, "loc": 12}],
        "source_text": {},
        "stats": {"files": 1, "loc": 12, "edges": 0, "truncated": False},
    }
    result = ask.answer("Focus on the main entry file.")
    assert "src/main.py" in result["say"]
    assert result["ui_commands"][0] == {"type": "focus", "path": "src/main.py"}


def test_http_ask_landmark_files():
    from fastapi.testclient import TestClient

    import app as friday_app
    import github_tools
    import map_pipeline

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "owner": "acme",
        "repo": "demo",
        "slug": "acme/demo",
        "branch": "main",
        "files": {
            "src/main.py": {
                "loc": 20,
                "kind": "code",
                "landmark": {"entry": True, "core": False, "hotspot": False},
                "imported_by": [],
                "imports": [],
            },
            "src/big.py": {
                "loc": 400,
                "kind": "code",
                "landmark": {"entry": False, "core": True, "hotspot": True},
                "imported_by": [],
                "imports": [],
            },
        },
        "landmarks": [
            {"path": "src/main.py", "loc": 20, "entry": True, "core": False, "hotspot": False},
            {"path": "src/big.py", "loc": 400, "entry": False, "core": True, "hotspot": True},
        ],
        "source_text": {},
        "stats": {"files": 2, "loc": 420, "edges": 0, "truncated": False},
    }
    client = TestClient(friday_app.app)
    response = client.post(
        "/api/ask",
        json={"question": "What are the landmark files in this repository?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("say")
    assert "src/main.py" in body["say"] and "src/big.py" in body["say"]
    assert body["steps"][0]["detail"] == "list_landmarks"


def test_friday_turn_matches_ask():
    import chat
    import github_tools
    import map_pipeline
    import orchestrator

    github_tools.set_active_repo("acme/demo")
    map_pipeline._cache["acme/demo@default"] = {
        "owner": "acme",
        "repo": "demo",
        "slug": "acme/demo",
        "files": {"src/main.py": {"loc": 12, "kind": "code", "landmark": {"entry": True, "core": False, "hotspot": False}, "imported_by": [], "imports": []}},
        "landmarks": [{"path": "src/main.py", "loc": 12, "entry": True, "core": False, "hotspot": False}],
        "source_text": {},
        "stats": {"files": 1, "loc": 12, "edges": 0, "truncated": False},
    }
    question = "What are the landmark files in this repository?"
    via_chat = chat.turn(question)
    via_voice = orchestrator.dispatch(
        "friday_turn",
        {"utterance": question},
        question,
        "voice-parity",
    )
    assert via_voice.get("say")
    assert via_chat["say"] == via_voice["say"]


if __name__ == "__main__":
    test_imports_and_landmarks()
    test_gate_blocks_false_safe()
    test_confident_approve_clears_without_a_reader()
    test_unsure_verdict_needs_a_reader()
    test_sign_in_restores_and_answers_link_out()
    test_confirm_without_github_keeps_the_draft()
    test_write_needs_a_later_yes()
    test_every_voice_tool_returns_say()
    test_confident_block_skips_readers()
    test_gemini_error_falls_through_to_k2()
    test_voice_prompt_names_the_open_repo()
    test_map_question_describes_the_fingerprint()
    test_landmarks_and_largest_file_are_grounded()
    test_ask_runs_the_tool_the_model_calls()
    test_tool_error_does_not_quote_files()
    test_focus_command_can_call_focus_file()
    test_turn_explains_the_focused_file_without_k2()
    test_focus_does_not_explain_and_a_purpose_question_does()
    test_explain_project_reads_the_readme()
    test_give_up_is_honest()
    test_production_scenarios()
    test_http_ask_landmark_files()
    test_friday_turn_matches_ask()
    print("ok")
