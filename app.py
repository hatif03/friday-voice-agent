"""Friday — voice control surface.

Run: python app.py
Then open http://localhost:5000
"""
import asyncio
import os
import tempfile

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()
print(f"[startup] .env resolved to: {find_dotenv() or '(none found)'}")
print(f"[startup] GITHUB_REPO = {os.environ.get('GITHUB_REPO')!r}")
print(f"[startup] AGENT_LLM_PROVIDER = {(os.environ.get('AGENT_LLM_PROVIDER') or 'assemblyai')!r}")

from agent import run_agent
from github_tools import (
    active_repo,
    begin_oauth,
    confirm_write,
    connect_github,
    disconnect_github,
    finish_oauth,
    github_status,
    list_accessible_repos,
    looks_like_yes,
    pending_write,
    set_active_repo,
    set_turn_context,
)
import map_pipeline
from orchestrator import dispatch
from transcribe import transcribe_audio
import voice_broker

app = FastAPI(title="Friday")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

if (os.environ.get("GITHUB_REPO") or "").strip():
    try:
        set_active_repo(os.environ["GITHUB_REPO"])
    except RuntimeError:
        pass


def _missing_env() -> list[str]:
    missing = [name for name in ("ASSEMBLYAI_API_KEY",) if not os.environ.get(name)]
    return missing


@app.get("/")
async def index(request: Request, repo: str = ""):
    return templates.TemplateResponse(request, "index.html", {"repo": repo})


@app.post("/api/run")
async def api_run(audio: UploadFile = File(...)):
    """Sync speech-to-text fallback. The live demo uses the Voice Agent socket."""
    if _missing_env():
        return JSONResponse({"error": "ASSEMBLYAI_API_KEY is missing. Check your .env file."}, status_code=500)
    raw = await audio.read()
    if not raw:
        return JSONResponse({"error": "No audio file uploaded."}, status_code=400)

    def _work():
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "instruction.wav")
            with open(wav_path, "wb") as handle:
                handle.write(raw)
            return transcribe_audio(wav_path)

    try:
        transcription = await asyncio.to_thread(_work)
    except Exception as exc:
        return JSONResponse({"error": f"Transcription failed: {exc}"}, status_code=502)

    transcript = (transcription.get("text") or "").strip()
    if not transcript:
        return JSONResponse({"error": "Got an empty transcript — try again and speak a bit longer."}, status_code=400)

    def _agent():
        set_turn_context(transcript, transcript)
        if pending_write() and looks_like_yes(transcript):
            posted = confirm_write(confirmed=True, transcript_id="api-run-new", user_transcript=transcript)
            if posted.get("status") == "posted":
                return {"summary": posted.get("say") or "Posted.", "tool_calls": [{"name": "confirm_write", "args": {}, "result": posted}]}
            if posted.get("status") == "cancelled":
                return {"summary": posted.get("say"), "tool_calls": [{"name": "confirm_write", "args": {}, "result": posted}]}
        return run_agent(transcript, transcript_id="api-run-new")

    try:
        agent_result = await asyncio.to_thread(_agent)
    except Exception as exc:
        return JSONResponse({"error": f"Agent failed: {exc}", "transcript": transcript}, status_code=502)
    return {
        "transcript": transcript,
        "tool_calls": agent_result["tool_calls"],
        "summary": agent_result["summary"],
    }


@app.get("/api/voice/session")
async def voice_session():
    if _missing_env():
        raise HTTPException(status_code=500, detail="ASSEMBLYAI_API_KEY is missing.")
    try:
        payload = await asyncio.to_thread(voice_broker.browser_bootstrap)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return payload


@app.post("/api/voice/tool")
async def voice_tool(request: Request):
    body = await request.json()
    name = body.get("name") or ""
    arguments = body.get("arguments") or {}
    transcript = body.get("user_transcript") or ""
    transcript_id = body.get("transcript_id") or ""

    def _call():
        return dispatch(name, arguments, transcript, transcript_id)

    result = await asyncio.to_thread(_call)
    return result


@app.get("/api/map")
async def get_map(repo: str):
    def _open():
        set_active_repo(repo)
        payload = map_pipeline.public_map(map_pipeline.open_repo(repo))
        payload["voice_prompt"] = voice_broker.system_prompt()
        payload["voice_keyterms"] = voice_broker.repo_keyterms()
        return payload

    try:
        return await asyncio.to_thread(_open)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/architecture")
async def architecture(request: Request):
    body = await request.json()
    repo = (body.get("repo") or "").strip()
    if repo:
        set_active_repo(repo)

    def _call():
        return dispatch("explain_architecture", {}, "", "ui")

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/github/oauth/start")
async def github_oauth_start(request: Request):
    try:
        url = begin_oauth(request.query_params.get("return") or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url)


@app.get("/api/github/callback")
async def github_oauth_callback(code: str = "", state: str = ""):
    def _call():
        return finish_oauth(code, state)

    try:
        signed_in = await asyncio.to_thread(_call)
    except Exception:
        return RedirectResponse("/?github=failed")
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    from github_tools import safe_return_path

    back = safe_return_path((signed_in or {}).get("return_to") or "/")
    parts = urlsplit(back)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["github"] = "connected"
    if "repo" not in query and active_repo():
        query["repo"] = active_repo()
    target = urlunsplit(("", "", parts.path or "/", urlencode(query), ""))
    return RedirectResponse(target)


@app.get("/api/github/repos")
async def github_repos():
    try:
        return await asyncio.to_thread(list_accessible_repos)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/github/connect")
async def github_connect(request: Request):
    body = await request.json()
    token = body.get("token") or ""

    def _call():
        return connect_github(token)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/github/disconnect")
async def github_disconnect():
    return await asyncio.to_thread(disconnect_github)


@app.get("/api/github/status")
async def github_who():
    return github_status()


@app.get("/api/history")
async def get_history(count: int = 30):
    import history

    def _call():
        return history.load_window(count)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ask")
async def api_ask(request: Request):
    import chat

    body = await request.json()

    def _call():
        return chat.turn(body.get("question") or "")

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/security")
async def api_security():
    import security

    def _call():
        return security.scan_open()

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "friday"}


if __name__ == "__main__":
    import uvicorn

    if _missing_env():
        raise SystemExit("ASSEMBLYAI_API_KEY is missing. Copy .env.example to .env and fill it in.")
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=False)
