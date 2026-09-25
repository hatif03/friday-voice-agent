"""Live Voice Agent session check. Skips when the API key is missing.

Confirms the stored agent binds with only agent_id, that configure carries
all 20 tools, and that the socket reaches session.ready without session.error.
It does not send speech.
"""
import asyncio
import json
import os

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    if not os.environ.get("ASSEMBLYAI_API_KEY"):
        print("skip")
        return
    import voice_broker
    from orchestrator import _HANDLERS

    payload = voice_broker.browser_bootstrap()
    bind = payload["session"]["session"]
    assert list(bind) == ["agent_id"], bind
    names = [tool["name"] for tool in payload["configure"]["session"]["tools"]]
    assert names == list(_HANDLERS), names
    assert payload["hold_tools"] == names
    asyncio.run(_ready(payload))
    print("ok", bind["agent_id"][:12])


async def _ready(payload: dict) -> None:
    import websockets

    async with websockets.connect(payload["ws_url"], open_timeout=20) as ws:
        await ws.send(json.dumps(payload["session"]))
        ready = False
        for _ in range(8):
            raw = await asyncio.wait_for(ws.recv(), timeout=20)
            message = json.loads(raw)
            if message.get("type") == "session.error":
                raise RuntimeError(message.get("message") or message.get("error") or "session.error")
            if message.get("type") == "session.ready":
                ready = True
                break
        if not ready:
            raise RuntimeError("session.ready did not arrive")
        await ws.send(json.dumps(payload["configure"]))
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
        except asyncio.TimeoutError:
            return
        message = json.loads(raw)
        if message.get("type") == "session.error":
            raise RuntimeError(message.get("message") or message.get("error") or "configure failed")


if __name__ == "__main__":
    main()
