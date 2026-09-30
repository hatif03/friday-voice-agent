"""Deploy Friday to Google Cloud Run from the repo root.

Reads .env (never committed) and passes vars to gcloud. Updates GITHUB_OAUTH_CALLBACK
to the service URL after the first deploy when it still points at localhost.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_YAML = ROOT / "cloudrun-env.yaml"


def gcloud_bin() -> str:
    for name in ("gcloud.cmd", "gcloud"):
        found = shutil.which(name)
        if found:
            return found
    win = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google"
        / "Cloud SDK"
        / "google-cloud-sdk"
        / "bin"
        / "gcloud.cmd"
    )
    if win.is_file():
        return str(win)
    return "gcloud"


def gcloud(*args: str) -> list[str]:
    return [gcloud_bin(), *args]


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            out[key] = value
    return out


def write_env_yaml(variables: dict[str, str], path: Path) -> None:
    lines = []
    for key in sorted(variables):
        safe = variables[key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}: "{safe}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="", help="GCP project id")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--service", default="friday-voice-agent")
    parser.add_argument("--skip-env", action="store_true", help="Do not push .env to Cloud Run")
    args = parser.parse_args()

    project = args.project.strip()
    if not project:
        proc = subprocess.run(
            gcloud("config", "get-value", "project"),
            capture_output=True,
            text=True,
            check=False,
        )
        project = (proc.stdout or "").strip()
    if not project:
        print("No GCP project. Run: gcloud config set project YOUR_PROJECT", file=sys.stderr)
        return 1

    run(
        gcloud(
            "services",
            "enable",
            "run.googleapis.com",
            "cloudbuild.googleapis.com",
            "artifactregistry.googleapis.com",
            "--project",
            project,
        )
    )

    deploy_cmd = gcloud(
        "run",
        "deploy",
        args.service,
        "--source",
        str(ROOT),
        "--project",
        project,
        "--region",
        args.region,
        "--allow-unauthenticated",
        "--port",
        "8080",
        "--memory",
        "2Gi",
        "--cpu",
        "2",
        "--timeout",
        "300",
        "--max-instances",
        "5",
    )

    if not args.skip_env and ENV_FILE.is_file():
        variables = parse_dotenv(ENV_FILE)
        variables.pop("GITHUB_OAUTH_CALLBACK", None)
        write_env_yaml(variables, ENV_YAML)
        deploy_cmd.extend(["--env-vars-file", str(ENV_YAML)])

    run(deploy_cmd)

    def service_urls() -> list[str]:
        url_proc = subprocess.run(
            gcloud(
                "run",
                "services",
                "describe",
                args.service,
                "--project",
                project,
                "--region",
                args.region,
                "--format",
                "json",
            ),
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(url_proc.stdout or "{}")
        annotations = (payload.get("metadata") or {}).get("annotations") or {}
        raw = annotations.get("run.googleapis.com/urls") or "[]"
        try:
            listed = json.loads(raw)
        except json.JSONDecodeError:
            listed = []
        urls = [str(u).rstrip("/") for u in listed if u]
        if not urls:
            status_url = ((payload.get("status") or {}).get("url") or "").strip().rstrip("/")
            if status_url:
                urls = [status_url]
        return urls

    def canonical_service_url(urls: list[str]) -> str:
        """Prefer the stable *-{projectNumber}.{region}.run.app hostname."""
        pattern = re.compile(r"-\d+\.[a-z0-9-]+\.run\.app$", re.I)
        for url in urls:
            host = url.split("://", 1)[-1].split("/", 1)[0]
            if pattern.search(host):
                return url
        return urls[0] if urls else ""

    base = canonical_service_url(service_urls())
    if not base:
        print("Could not resolve Cloud Run service URL.", file=sys.stderr)
        return 1
    callback = f"{base}/api/github/callback"

    run(
        gcloud(
            "run",
            "services",
            "update",
            args.service,
            "--project",
            project,
            "--region",
            args.region,
            "--update-env-vars",
            f"GITHUB_OAUTH_CALLBACK={callback}",
        )
    )

    all_urls = service_urls()
    print(f"\nDeployed (canonical): {base}")
    if len(all_urls) > 1:
        print("Also reachable at:", ", ".join(u for u in all_urls if u != base))
    print(f"Set GitHub OAuth callback to: {base}/api/github/callback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
