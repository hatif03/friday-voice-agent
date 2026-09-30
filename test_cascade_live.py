"""One live review of a tiny diff. Skips when a key is missing.

Checks that the trace says accept or escalate, and that the spoken line
comes from the model that decided. No speech is sent.
"""
import os

from dotenv import load_dotenv

load_dotenv()


DIFF = "FILE src/app.py\n@@ -1 +1 @@\n-print(0)\n+print(1)\n"


def main() -> None:
    if not os.environ.get("TYPESAFE_API_KEY") or not os.environ.get("ASSEMBLYAI_API_KEY"):
        print("skip")
        return
    from orchestrator import judge_change

    judged = judge_change("Print one", "", DIFF, ["src/app.py"], {"src/app.py"})
    route = judged["route"]
    decided_by = judged["decided_by"]
    say = judged["gate"]["say"]
    assert route in ("accept", "escalate"), route
    if route == "accept":
        assert decided_by == "jev"
    else:
        assert decided_by in ("vertex", "k2"), decided_by
    assert say
    assert judged["gate"]["decided_by"] == decided_by
    print("ok", route, decided_by)


if __name__ == "__main__":
    main()
