"""Read-only MCP server over the same map and review tools.

Run: python mcp_server.py
Writes (issues, comments) are not exposed.
"""
import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

import map_pipeline
from github_tools import get_commit_diff, list_recent_commits, set_active_repo
import jev_gate
import review_gate
import specialists

mcp = MCPServer("friday")


def _open(repo: str) -> dict:
    set_active_repo(repo)
    return map_pipeline.open_repo(repo)


@mcp.tool()
def summarize_map(repo: str) -> str:
    """Describe the fingerprint of a public GitHub repository (owner/name)."""
    payload = _open(repo)
    return map_pipeline.landmark_brief(payload)


@mcp.tool()
def focus_file(repo: str, path: str) -> str:
    """Return landmark, import, and size facts for one file on the map."""
    payload = _open(repo)
    meta = payload["files"].get(path)
    if meta is None:
        return f"{path} is not in the fingerprint for {repo}."
    flags = [name for name, on in meta["landmark"].items() if on] or ["none"]
    return (
        f"{path}: {meta['loc']} lines, kind {meta['kind']}, landmark {', '.join(flags)}. "
        f"Imports {len(meta['imports'])}. Imported by {len(meta['imported_by'])}."
    )


@mcp.tool()
def review_diff(repo: str, sha: str = "") -> str:
    """Score the latest commit, or a given SHA, with Jev. Does not post anything."""
    payload = _open(repo)
    if not sha:
        commits = list_recent_commits(1)
        if not commits["commits"]:
            return "No commits."
        sha = commits["commits"][0]["sha"]
    commit = get_commit_diff(sha)
    diff = "\n".join(f"{item.get('filename')}\n{item.get('patch') or ''}" for item in commit.get("files") or [])
    review = jev_gate.review_change(commit.get("message") or sha, "", diff)
    draft = specialists.gateway_draft(diff[:12000])
    gate = review_gate.validate_review(
        jev=review,
        draft=draft,
        known_paths=set(payload["files"]),
        second_reads=[],
        second_reads_required=jev_gate.needs_second_reader(review),
    )
    return gate["say"]


if __name__ == "__main__":
    os.environ.setdefault("FASTMCP_PORT", "8000")
    mcp.run()
