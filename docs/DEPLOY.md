# Deploy to Google Cloud Run

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- `gcloud auth login` and `gcloud config set project YOUR_PROJECT`
- Billing enabled on the project
- `.env` filled in at repo root (not committed)

## One-command deploy

From the repo root:

```bash
python scripts/deploy_cloudrun.py
```

Optional flags: `--project`, `--region` (default `us-central1`), `--service` (default `friday-voice-agent`).

The script:

1. Enables Cloud Run, Cloud Build, and Artifact Registry APIs
2. Builds the container from `Dockerfile` via `gcloud run deploy --source`
3. Loads non-empty variables from `.env` into the service
4. Sets `GITHUB_OAUTH_CALLBACK` to the **canonical** hostname (`https://<service>-<project-number>.<region>.run.app/api/github/callback`), not the alternate `*.a.run.app` URL Cloud Run also exposes

Cloud Run serves the same revision on both hostnames; keep GitHub OAuth and docs on the canonical `*-147606977567.us-central1.run.app` link so sign-in matches `GITHUB_OAUTH_CALLBACK`.

## After deploy

1. In your [GitHub OAuth app](https://github.com/settings/developers), set **Homepage URL** and **Authorization callback URL** to the callback printed by the script.
2. Open the service URL with `?repo=owner/name`.
3. Health check: `GET /api/health`
4. Demo GIF (if shipped in the image): `GET /assets/demo.gif`

## Manual deploy

```bash
gcloud run deploy friday-voice-agent --source . --region us-central1 --allow-unauthenticated --port 8080 --memory 2Gi --cpu 2 --timeout 300
```

## Notes

- Ephemeral disk: `.friday_agent_id` and `.github_session` reset on new revisions; OAuth users re-sign-in after redeploy unless you add persistent storage.
- Mic requires HTTPS (Cloud Run provides this).
- Increase `--timeout` (max 3600) if long Gateway agent runs time out.
