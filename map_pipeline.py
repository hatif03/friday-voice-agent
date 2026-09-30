"""Repository fingerprint pipeline.

Ingest a GitHub tarball, classify files, resolve local imports, mark
landmarks, and return a tree the browser circle-packs. No language model.
"""
import io
import os
import re
import tarfile
from collections import defaultdict

import requests

MAX_FILES = 500
MAX_EDGES = 900
MAX_FILE_BYTES = 1_500_000

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "vendor", "__pycache__",
    ".next", "coverage", "target", ".venv", "venv", "out", ".cache",
    "site-packages", ".pytest_cache",
}
SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs",
    ".java", ".rb", ".php", ".cs", ".kt", ".swift", ".c", ".h", ".hpp",
    ".cc", ".cpp", ".md", ".html", ".css", ".scss", ".vue", ".svelte",
}
EXT_COLOR = {
    ".py": "#FFC312", ".js": "#6473F2", ".jsx": "#6473F2", ".mjs": "#6473F2",
    ".cjs": "#6473F2", ".ts": "#22a6b3", ".tsx": "#22a6b3", ".md": "#CED6E0",
    ".json": "#FDA7DF", ".yml": "#e17055", ".yaml": "#e17055", ".html": "#e17055",
    ".css": "#badc58", ".scss": "#badc58", ".go": "#00b894", ".rs": "#e17055",
    ".sh": "#6c5ce7", ".svg": "#fd79a8", ".png": "#fd79a8",
}
DISTRICT_COLORS = [
    "#CE83F1", "#6473F2", "#badc58", "#FDA7DF", "#FFC312",
    "#22a6b3", "#e17055", "#6c5ce7", "#00b894", "#fd79a8",
]
ENTRY_NAMES = {
    "index.js", "index.ts", "index.tsx", "index.jsx", "main.py", "app.py",
    "main.js", "main.ts", "main.go", "lib.rs", "main.rs", "manage.py",
    "wsgi.py", "server.py", "app.tsx", "page.tsx",
}
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"\n]+?\s+from\s+)?|export\s+[^'"\n]+?\s+from\s+|require\(\s*)['"]([^'"]+)['"]"""
)
PY_IMPORT = re.compile(r"^(?:from\s+(\.+)?([\w.]+)\s+import|import\s+([\w.]+))", re.M)

_cache: dict[str, dict] = {}


def _top(path: str) -> str:
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def _kind(path: str) -> str:
    lower = path.lower()
    name = os.path.basename(lower)
    if any(token in lower for token in ("/test/", "/tests/", "__tests__", ".test.", ".spec.")):
        return "test"
    if name.startswith("readme") or lower.endswith((".md", ".rst")) or "/docs/" in f"/{lower}":
        return "docs"
    if any(token in name for token in ("config", "dockerfile", ".json", ".yml", ".yaml", ".toml", ".ini")):
        return "config"
    if lower.endswith((".png", ".jpg", ".svg", ".gif", ".webp", ".ico")):
        return "asset"
    return "source"


def _skipped(path: str) -> bool:
    parts = path.split("/")
    return any(part in SKIP_DIRS or part.startswith(".") and part not in {".github"} for part in parts[:-1])


def _decode(raw: bytes) -> str | None:
    if b"\x00" in raw[:1024]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def _is_source(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in SOURCE_EXT or os.path.basename(path).lower().startswith("readme")


def _module_index(known: set[str]) -> dict[str, str]:
    """Map a Python module suffix to one real path, shortest path first."""
    index: dict[str, str] = {}
    for path in sorted(known, key=len):
        if not path.endswith(".py"):
            continue
        module = path[:-3]
        if module.endswith("/__init__"):
            module = module[: -len("/__init__")]
        parts = module.replace("/", ".").split(".")
        for start in range(len(parts)):
            index.setdefault(".".join(parts[start:]), path)
    return index


def parse_files(blobs: dict[str, bytes]) -> dict:
    """Build the fingerprint from path -> bytes. Pure function, used by tests."""
    catalog = []
    for path, raw in blobs.items():
        path = path.replace("\\", "/").lstrip("./")
        if not path or path.endswith("/") or _skipped(path):
            continue
        if len(raw) > MAX_FILE_BYTES:
            continue
        catalog.append((path, raw))
    known = {path for path, _raw in catalog}
    module_index = _module_index(known)
    scanned_texts: dict[str, str] = {}
    for path, raw in sorted(catalog, key=lambda item: (0 if _is_source(item[0]) else 1, len(item[1]))):
        if len(scanned_texts) >= 2500:
            break
        if not _is_source(path):
            continue
        text = _decode(raw)
        if text is not None:
            scanned_texts[path] = text
    indegree: dict[str, int] = defaultdict(int)
    outdegree: dict[str, int] = defaultdict(int)
    discovered = []
    seen_edges = set()
    for path, text in scanned_texts.items():
        for target in _resolve_imports(path, text, known, module_index):
            key = (path, target)
            if key in seen_edges or target == path:
                continue
            seen_edges.add(key)
            discovered.append(key)
            indegree[target] += 1
            outdegree[path] += 1
            if len(discovered) >= MAX_EDGES * 4:
                break
    catalog.sort(
        key=lambda item: (
            indegree[item[0]] + outdegree[item[0]],
            1 if os.path.basename(item[0]) in ENTRY_NAMES else 0,
            1 if _is_source(item[0]) else 0,
            len(item[1]),
        ),
        reverse=True,
    )
    truncated = len(catalog) > MAX_FILES
    chosen = list(catalog[:MAX_FILES])
    chosen_paths = {path for path, _raw in chosen}
    for path, raw in catalog:
        if os.path.basename(path).lower().startswith("readme") and path not in chosen_paths:
            chosen.append((path, raw))
            chosen_paths.add(path)
    kept = [(0, len(raw), path, raw) for path, raw in chosen]
    kept_paths = {path for _score, _size, path, _raw in kept}
    files = {}
    texts = {}
    for _score, size, path, raw in kept:
        text = _decode(raw)
        loc = 0
        if text is not None:
            loc = sum(1 for line in text.splitlines() if line.strip())
            texts[path] = text
        ext = os.path.splitext(path)[1].lower()
        files[path] = {
            "path": path,
            "size": size,
            "loc": loc,
            "ext": ext or "(none)",
            "kind": _kind(path),
            "language": ext.lstrip(".") or "file",
            "imports": [],
            "imported_by": [],
            "heat": 0,
            "landmark": {"entry": False, "core": False, "hotspot": False},
            "color": EXT_COLOR.get(ext, "#9aa0a6"),
        }

    edges = []
    for source, target in discovered:
        if source in kept_paths and target in kept_paths:
            edges.append({"source": source, "target": target})
        if len(edges) >= MAX_EDGES:
            break
    for edge in edges:
        files[edge["source"]]["imports"].append(edge["target"])
        files[edge["target"]]["imported_by"].append(edge["source"])

    _annotate(files)
    tree = _tree(files)
    landmarks = [
        {
            "path": path,
            "loc": meta["loc"],
            "in_degree": len(meta["imported_by"]),
            "entry": meta["landmark"]["entry"],
            "core": meta["landmark"]["core"],
            "hotspot": meta["landmark"]["hotspot"],
        }
        for path, meta in files.items()
        if any(meta["landmark"].values())
    ]
    return {
        "stats": {
            "files": len(files),
            "folders": _folder_count(tree),
            "loc": sum(meta["loc"] for meta in files.values()),
            "truncated": truncated,
            "edges": len(edges),
            "languages": _language_mix(files),
        },
        "landmarks": landmarks,
        "edges": edges,
        "tree": tree,
        "files": files,
        "source_text": _snippets(texts),
    }


def _snippets(texts: dict) -> dict:
    """Short excerpts for later questions and checks. Not sent to the browser."""
    def rank(path: str) -> tuple:
        base = os.path.basename(path).lower()
        if base.startswith("readme"):
            return (0, path)
        if base in {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "setup.py", "composer.json"}:
            return (1, path)
        return (2, path)

    kept = {}
    for path, text in sorted(texts.items(), key=lambda item: rank(item[0])):
        if len(kept) >= 160:
            break
        lower = path.lower()
        if lower.endswith((".lock", ".min.js", ".min.css", ".map")):
            continue
        if text:
            limit = 8000 if os.path.basename(path).lower().startswith("readme") else 5000
            kept[path] = text[:limit]
    return kept


def _resolve_imports(path: str, text: str, known: set[str], module_index: dict[str, str] | None = None) -> list[str]:
    ext = os.path.splitext(path)[1].lower()
    found = []
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        for match in JS_IMPORT.finditer(text):
            spec = match.group(1)
            if not spec.startswith("."):
                continue
            resolved = _resolve_relative(path, spec, known)
            if resolved:
                found.append(resolved)
    elif ext == ".py":
        for match in PY_IMPORT.finditer(text):
            dots, dotted, plain = match.group(1), match.group(2), match.group(3)
            module = dotted or plain or ""
            if dots:
                up = len(dots)
                base = path.split("/")[:-up]
                parts = [part for part in module.split(".") if part]
                candidate = "/".join(base + parts)
            else:
                candidate = module.replace(".", "/")
            resolved = _py_candidate(candidate, known, module_index)
            if resolved:
                found.append(resolved)
    return found


def _resolve_relative(path: str, spec: str, known: set[str]) -> str | None:
    folder = path.split("/")[:-1]
    parts = folder[:]
    for piece in spec.split("/"):
        if piece == "." or piece == "":
            continue
        if piece == "..":
            if parts:
                parts.pop()
            continue
        parts.append(piece)
    base = "/".join(parts)
    options = [base]
    root, ext = os.path.splitext(base)
    if not ext:
        options = [
            base + suffix
            for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".py")
        ] + [base + "/index.ts", base + "/index.tsx", base + "/index.js", base + "/index.jsx"]
    for option in options:
        if option in known:
            return option
    return None


def _py_candidate(candidate: str, known: set[str], module_index: dict[str, str] | None = None) -> str | None:
    for option in (candidate + ".py", candidate + "/__init__.py"):
        if option in known:
            return option
    if module_index:
        return module_index.get(candidate.replace("/", "."))
    return None


def _annotate(files: dict) -> None:
    entries = []
    for path, meta in files.items():
        name = os.path.basename(path)
        if name in ENTRY_NAMES or name in {"__main__.py", "mod.rs"}:
            entries.append(path)
    entries.sort(key=lambda path: files[path]["imported_by"].__len__(), reverse=True)
    for path in entries[:12]:
        files[path]["landmark"]["entry"] = True

    by_in = sorted(files, key=lambda path: len(files[path]["imported_by"]), reverse=True)
    core = 0
    for path in by_in:
        if len(files[path]["imported_by"]) < 2:
            break
        if files[path]["landmark"]["entry"]:
            continue
        files[path]["landmark"]["core"] = True
        core += 1
        if core >= 22:
            break

    by_loc = sorted(files, key=lambda path: files[path]["loc"], reverse=True)
    hot = 0
    for path in by_loc:
        if files[path]["loc"] < 40:
            break
        files[path]["landmark"]["hotspot"] = True
        hot += 1
        if hot >= 16:
            break


def _tree(files: dict) -> dict:
    root = {"name": "", "path": "", "children": [], "size": 0, "loc": 0}
    index = {"": root}
    districts = sorted({_top(path) for path in files})
    district_color = {name: DISTRICT_COLORS[i % len(DISTRICT_COLORS)] for i, name in enumerate(districts)}

    for path, meta in sorted(files.items()):
        parts = path.split("/")
        parent = root
        acc = ""
        for part in parts[:-1]:
            acc = f"{acc}/{part}" if acc else part
            if acc not in index:
                node = {
                    "name": part,
                    "path": acc,
                    "children": [],
                    "size": 0,
                    "loc": 0,
                    "folder": True,
                    "color": district_color.get(acc.split("/")[0], DISTRICT_COLORS[0]),
                }
                index[acc] = node
                parent["children"].append(node)
            parent = index[acc]
        leaf = {
            "name": parts[-1],
            "path": path,
            "size": max(meta["size"], 1),
            "loc": meta["loc"],
            "kind": meta["kind"],
            "ext": meta["ext"],
            "color": meta["color"],
            "landmark": meta["landmark"],
            "heat": meta["heat"],
            "folder": False,
        }
        parent["children"].append(leaf)
    return root


def _language_mix(files: dict) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for meta in files.values():
        counts[meta["language"]] += 1
    total = sum(counts.values()) or 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]
    return [{"name": name, "count": count, "share": round(count / total, 3)} for name, count in ranked]


def _folder_count(node: dict) -> int:
    count = 1 if node.get("folder") else 0
    for child in node.get("children") or []:
        count += _folder_count(child)
    return count


def _strip_tar_root(name: str) -> str:
    parts = name.split("/")
    if len(parts) <= 1:
        return ""
    return "/".join(parts[1:])


def fetch_tarball(owner: str, repo: str, branch: str | None = None) -> tuple[str, dict[str, bytes]]:
    headers = {"User-Agent": "friday-voice-agent", "Accept": "application/vnd.github+json"}
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    meta = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=30)
    if not meta.ok:
        if meta.status_code == 403:
            raise RuntimeError(f"GitHub refused {owner}/{repo} (403). Connect GitHub to lift the anonymous rate limit.")
        raise RuntimeError(f"GitHub could not open {owner}/{repo} ({meta.status_code}).")
    branch = branch or (meta.json() or {}).get("default_branch") or "main"
    archive = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/tarball/{branch}",
        headers=headers,
        timeout=120,
    )
    if not archive.ok:
        if archive.status_code == 403:
            raise RuntimeError(f"GitHub refused the download of {owner}/{repo} (403). Connect GitHub and try again.")
        raise RuntimeError(f"Could not download {owner}/{repo} ({archive.status_code}).")
    blobs = {}
    with tarfile.open(fileobj=io.BytesIO(archive.content), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            path = _strip_tar_root(member.name)
            if not path or _skipped(path):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            blobs[path] = extracted.read(MAX_FILE_BYTES + 1)
    return branch, blobs


def apply_heat(fingerprint: dict, owner: str, repo: str) -> None:
    headers = {"User-Agent": "friday-voice-agent", "Accept": "application/vnd.github+json"}
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    commits = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/commits",
        headers=headers,
        params={"per_page": 8},
        timeout=30,
    )
    if not commits.ok:
        return
    heat = defaultdict(int)
    for commit in commits.json() or []:
        sha = commit.get("sha")
        if not sha:
            continue
        detail = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}",
            headers=headers,
            timeout=30,
        )
        if not detail.ok:
            continue
        for item in (detail.json() or {}).get("files") or []:
            filename = item.get("filename")
            if filename in fingerprint["files"]:
                heat[filename] += 1
    for path, count in heat.items():
        fingerprint["files"][path]["heat"] = count
        _paint_heat(fingerprint["tree"], path, count)


def _paint_heat(node: dict, path: str, heat: int) -> bool:
    if node.get("path") == path and not node.get("folder", False) and node.get("name"):
        node["heat"] = heat
        return True
    for child in node.get("children") or []:
        if _paint_heat(child, path, heat):
            return True
    return False


def keyterms_for(owner: str, repo: str, fingerprint: dict) -> list[str]:
    names = [owner, repo, "hotspot", "blast radius", "Friday"]
    for landmark in fingerprint["landmarks"][:40]:
        names.append(os.path.basename(landmark["path"]))
        names.append(landmark["path"])
    deduped = []
    seen = set()
    for name in names:
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        deduped.append(name[:50])
        if len(deduped) >= 80:
            break
    return deduped


def open_repo(repo_slug: str) -> dict:
    """Download, parse, and cache a repository fingerprint."""
    ref = parse_github_ref(repo_slug)
    owner, repo = ref["owner"], ref["repo"]
    slug = f"{owner}/{repo}"
    cache_key = f"{slug}@{ref['branch'] or 'default'}"
    if cache_key in _cache:
        cached = _cache[cache_key]
        cached["focus_path"] = ref["path"] if ref["path"] in cached.get("files", {}) else None
        cached["pull_number"] = ref["pull"]
        return cached
    branch, blobs = fetch_tarball(owner, repo, ref["branch"])
    fingerprint = parse_files(blobs)
    try:
        apply_heat(fingerprint, owner, repo)
    except requests.RequestException:
        pass
    readme = ""
    for candidate in ("README.md", "README.rst", "readme.md", "Readme.md"):
        meta = fingerprint["files"].get(candidate)
        if meta:
            readme = candidate
            break
    focus = ref["path"] if ref["path"] in fingerprint["files"] else None
    payload = {
        "owner": owner,
        "repo": repo,
        "slug": slug,
        "branch": branch,
        "readme_path": readme,
        "focus_path": focus,
        "pull_number": ref["pull"],
        "keyterms": keyterms_for(owner, repo, fingerprint),
        **fingerprint,
    }
    _cache[cache_key] = payload
    os.makedirs("cache", exist_ok=True)
    try:
        import store

        store.record_repo(slug, branch or payload.get("branch") or "")
    except Exception:
        pass
    return payload


def get_cached(repo_slug: str) -> dict | None:
    try:
        ref = parse_github_ref(repo_slug)
    except RuntimeError:
        return None
    cache_key = f"{ref['owner']}/{ref['repo']}@{ref['branch'] or 'default'}"
    payload = _cache.get(cache_key)
    if payload is None:
        return None
    payload["focus_path"] = ref["path"] if ref["path"] in payload.get("files", {}) else payload.get("focus_path")
    payload["pull_number"] = ref["pull"]
    return payload


def parse_github_ref(repo_slug: str) -> dict:
    """Accept owner/name, a github.com URL, /tree, /blob, or /pull."""
    slug = (repo_slug or "").strip().strip("/")
    slug = re.sub(r"^https?://github\.com/", "", slug, flags=re.I)
    slug = slug.split("?", 1)[0].split("#", 1)[0].strip("/")
    slug = slug.removesuffix(".git")
    parts = [part for part in slug.split("/") if part]
    if len(parts) < 2:
        raise RuntimeError("Paste a GitHub link, or owner/name.")
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("That does not look like a GitHub repository.")
    ref = {"owner": owner, "repo": repo, "branch": None, "path": None, "pull": None}
    kind = parts[2] if len(parts) > 2 else ""
    if kind == "tree" and len(parts) >= 4:
        ref["branch"] = parts[3]
        ref["path"] = "/".join(parts[4:]) or None
    elif kind == "blob" and len(parts) >= 5:
        ref["branch"] = parts[3]
        ref["path"] = "/".join(parts[4:])
    elif kind == "pull" and len(parts) >= 4 and parts[3].isdigit():
        ref["pull"] = int(parts[3])
    elif kind in {"issues", "commit", "commits"}:
        pass
    elif kind:
        raise RuntimeError("Paste owner/name, or a GitHub tree, blob, or pull link.")
    return ref


def _split(repo_slug: str) -> tuple[str, str]:
    ref = parse_github_ref(repo_slug)
    return ref["owner"], ref["repo"]


def public_map(payload: dict) -> dict:
    """Drop bulky import lists from the wire copy the browser renders."""
    files = {}
    for path, meta in payload["files"].items():
        files[path] = {
            "path": path,
            "size": meta["size"],
            "loc": meta["loc"],
            "ext": meta["ext"],
            "kind": meta["kind"],
            "language": meta["language"],
            "imports": meta["imports"][:40],
            "imported_by": meta["imported_by"][:40],
            "heat": meta["heat"],
            "landmark": meta["landmark"],
            "color": meta["color"],
            "url": f"https://github.com/{payload['owner']}/{payload['repo']}/blob/{payload['branch']}/{path}",
        }
    return {
        "owner": payload["owner"],
        "repo": payload["repo"],
        "slug": payload["slug"],
        "branch": payload["branch"],
        "stats": payload["stats"],
        "landmarks": payload["landmarks"],
        "edges": payload["edges"],
        "tree": payload["tree"],
        "files": files,
        "keyterms": payload["keyterms"],
        "focus_path": payload.get("focus_path"),
        "pull_number": payload.get("pull_number"),
    }


def explain_map(payload: dict) -> str:
    """Say what the circle map is showing, not a diagram inside the source."""
    return (
        landmark_brief(payload)
        + " Bigger circles are larger files. Colour is the language."
        + " A ring marks an entry point, a core file, or a hotspot."
    )


def landmark_brief(payload: dict) -> str:
    bits = [
        f"{payload['slug']} has {payload['stats']['files']} files in view, "
        f"{payload['stats']['loc']} lines, {payload['stats']['edges']} import links."
    ]
    if payload["stats"]["truncated"]:
        bits.append("The map keeps entry points and the files those imports touch, up to 500.")
    named = payload["landmarks"][:8]
    if named:
        bits.append("Landmarks: " + ", ".join(item["path"] for item in named) + ".")
    return " ".join(bits)
