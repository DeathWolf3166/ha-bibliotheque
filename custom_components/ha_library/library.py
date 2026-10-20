"""Library storage: local folder in /config and GitHub repositories.

Layout of a library (local folder or repository, optionally under a sub-path):
  library.json                     index (package manifests, views, resources, instances)
  packages/<id>/package.yaml       Home Assistant package
  packages/<id>/manifest.json      dependencies and metadata
  packages/<id>/items.json         per-item view (names, YAML, dependencies) for the panel
  packages/<id>/files/<path>       pyscript / python_scripts / blueprints shipped with it
  views/<id>.yaml                  dashboard views
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CACHE_DIR, LOCAL_DIR

_LOGGER = logging.getLogger(__name__)
FORMAT = 1
MAX_ZIP = 60 * 1024 * 1024
GH_API = "https://api.github.com"


class LibraryError(Exception):
    """User-facing library error (message in French)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- reading
def read_library(root: Path) -> dict:
    """Return the index of a library folder (tolerates folders without library.json)."""
    if not root.exists():
        return {"format": FORMAT, "packages": [], "views": [], "resources": [], "instances": []}
    idx_path = root / "library.json"
    if idx_path.exists():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    else:
        idx = {"format": FORMAT, "packages": [], "views": [], "resources": [], "instances": []}
        for m in sorted((root / "packages").glob("*/manifest.json")) if (root / "packages").is_dir() else []:
            idx["packages"].append(json.loads(m.read_text(encoding="utf-8")))
    for p in idx.get("packages", []):
        _normalize(p)
    return idx


def _normalize(p: dict) -> None:
    p.setdefault("requires", p.pop("requires_packages", []) if "requires_packages" in p else [])
    for k in ("contexts", "integrations", "entities_to_provide", "notify_targets", "missing_on_source", "device_ids", "secrets", "files", "provides", "items"):
        p.setdefault(k, [])
    p.setdefault("counts", {})
    p.setdefault("version", "")
    p.setdefault("description", "")


def read_package(root: Path, pkg_id: str) -> dict:
    d = root / "packages" / pkg_id
    if not (d / "package.yaml").exists():
        raise LibraryError(f"Package « {pkg_id} » introuvable dans la bibliothèque.")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").exists() else {"id": pkg_id}
    _normalize(manifest)
    out = dict(manifest)
    out["yaml"] = (d / "package.yaml").read_text(encoding="utf-8")
    out["items_detail"] = json.loads((d / "items.json").read_text(encoding="utf-8")) if (d / "items.json").exists() else []
    files = {}
    fdir = d / "files"
    if fdir.is_dir():
        for f in fdir.rglob("*"):
            if f.is_file():
                files[f.relative_to(fdir).as_posix()] = f.read_text(encoding="utf-8", errors="replace")
    out["file_contents"] = files
    return out


def read_view(root: Path, view_id: str) -> str:
    p = root / "views" / f"{view_id}.yaml"
    if not p.exists():
        raise LibraryError("Vue introuvable.")
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- writing (export)
def write_export(root: Path, analysis: dict, snapshot: dict, package_ids: list[str]) -> dict:
    """Write selected packages of an analysis into a library folder and merge the index."""
    root.mkdir(parents=True, exist_ok=True)
    idx = read_library(root)
    by_id = {p["id"]: p for p in idx["packages"]}
    inst = snapshot["instance"]
    items = analysis["items"]
    snap_items = {i["uid"]: i for i in snapshot["items"]}
    written = []
    rename: dict[str, str] = {}
    for p in analysis["packages"]:
        if p["id"] not in package_ids:
            continue
        pid = p["id"]
        prev = by_id.get(pid)
        if prev and prev.get("source", {}).get("slug") not in (None, inst["slug"]):
            pid = f"{pid}-{inst['slug']}"
        rename[p["id"]] = pid
    for p in analysis["packages"]:
        if p["id"] not in rename:
            continue
        pid = rename[p["id"]]
        d = root / "packages" / pid
        if d.exists():
            shutil.rmtree(d)
        (d / "files").mkdir(parents=True)
        manifest = {k: v for k, v in p.items() if k not in ("yaml",)}
        manifest["id"] = pid
        manifest["requires"] = [rename.get(r, r) for r in p["requires"]]
        manifest["source"] = {"name": inst["name"], "slug": inst["slug"], "ha_version": inst["ha_version"], "exported_at": inst["exported_at"]}
        manifest["items_summary"] = [{"uid": u, "kind": items[u]["kind"], "name": items[u]["name"]} for u in p["items"]]
        (d / "package.yaml").write_text(p["yaml"], encoding="utf-8")
        (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "items.json").write_text(json.dumps([items[u] for u in p["items"]], ensure_ascii=False, indent=1), encoding="utf-8")
        for u in p["items"]:
            f = snap_items[u].get("file")
            if f:
                dest = d / "files" / f["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(f["content"], encoding="utf-8")
        by_id[pid] = {k: v for k, v in manifest.items() if k != "items_summary"}
        written.append(pid)
    # views
    vdir = root / "views"
    vdir.mkdir(exist_ok=True)
    views_idx = {v["id"]: v for v in idx.get("views", [])}
    for v in snapshot.get("views", []):
        vid = f"{inst['slug']}-{v['id']}"
        (vdir / f"{vid}.yaml").write_text(v["yaml"], encoding="utf-8")
        views_idx[vid] = {k: v[k] for k in ("dashboard", "dashboard_path", "title", "custom_cards", "entities")} | {"id": vid, "source": inst["slug"], "size": len(v["yaml"])}
    res = {r["url"]: r for r in idx.get("resources", [])}
    for r in snapshot.get("resources", []):
        res[r["url"]] = r
    insts = {i["slug"]: i for i in idx.get("instances", [])}
    insts[inst["slug"]] = {k: inst[k] for k in ("name", "slug", "ha_version", "exported_at", "entity_count")}
    idx = {
        "format": FORMAT, "name": idx.get("name") or "Bibliothèque HA", "updated": _now(),
        "packages": sorted(by_id.values(), key=lambda p: p.get("title", p["id"]).lower()),
        "views": sorted(views_idx.values(), key=lambda v: (v["dashboard"], v["title"])),
        "resources": sorted(res.values(), key=lambda r: r["url"]),
        "instances": sorted(insts.values(), key=lambda i: i["slug"]),
    }
    (root / "library.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Bibliothèque HA\n\nBibliothèque de packages Home Assistant gérée par l’intégration "
            "« Bibliothèque HA ». Chaque dossier de `packages/` contient un `package.yaml` prêt à "
            "installer et un `manifest.json` (dépendances, contextes, entités à fournir).\n",
            encoding="utf-8",
        )
    return {"written": written, "renamed": {k: v for k, v in rename.items() if k != v}}


def remove_package(root: Path, pkg_id: str) -> None:
    d = root / "packages" / pkg_id
    if d.exists():
        shutil.rmtree(d)
    idx = read_library(root)
    idx["packages"] = [p for p in idx["packages"] if p["id"] != pkg_id]
    idx["updated"] = _now()
    (root / "library.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- sources
def source_root(hass: HomeAssistant, source: dict) -> Path:
    base = Path(hass.config.path(LOCAL_DIR))
    if source["type"] == "local":
        return base / "library"
    safe = source["repo"].replace("/", "__")
    root = Path(hass.config.path(CACHE_DIR)) / safe
    sub = (source.get("path") or "").strip("/")
    return root / sub if sub else root


def _gh_headers(token: str | None) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ha-library"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def async_fetch_github(hass: HomeAssistant, source: dict) -> dict:
    """Download a GitHub repository into the cache. Returns {"files": n, "fetched_at": ...}."""
    repo, branch = source["repo"], source.get("branch") or "main"
    session = async_get_clientsession(hass)
    url = f"{GH_API}/repos/{repo}/zipball/{branch}"
    try:
        async with session.get(url, headers=_gh_headers(source.get("token")), timeout=ClientTimeout(total=120)) as resp:
            if resp.status == 404:
                raise LibraryError(f"Dépôt {repo} (branche {branch}) introuvable. S’il est privé, renseignez un jeton GitHub.")
            if resp.status in (401, 403):
                raise LibraryError(f"Accès refusé au dépôt {repo} : vérifiez le jeton GitHub.")
            if resp.status != 200:
                raise LibraryError(f"GitHub a répondu {resp.status} pour {repo}.")
            data = await resp.content.read(MAX_ZIP + 1)
    except ClientError as err:
        raise LibraryError(f"Téléchargement de {repo} impossible : {err}") from err
    if len(data) > MAX_ZIP:
        raise LibraryError("Dépôt trop volumineux (plus de 60 Mo).")

    def extract() -> int:
        safe = repo.replace("/", "__")
        root = Path(hass.config.path(CACHE_DIR)) / safe
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        n = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                parts = info.filename.split("/", 1)
                if len(parts) < 2 or not parts[1] or info.is_dir():
                    continue
                rel = Path(parts[1])
                if rel.is_absolute() or ".." in rel.parts:
                    continue
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(info))
                n += 1
        return n

    n = await hass.async_add_executor_job(extract)
    return {"files": n, "fetched_at": _now()}


async def async_publish_github(hass: HomeAssistant, local_root: Path, source: dict, message: str) -> dict:
    """Push the local library to a GitHub repository in a single commit."""
    repo, branch = source["repo"], source.get("branch") or "main"
    token = source.get("token")
    if not token:
        raise LibraryError("Un jeton GitHub avec le droit « Contents: write » est nécessaire pour publier.")
    prefix = (source.get("path") or "").strip("/")
    session = async_get_clientsession(hass)
    h = _gh_headers(token)

    def collect() -> list[dict]:
        out = []
        for f in sorted(local_root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(local_root).as_posix()
                out.append({"path": f"{prefix}/{rel}" if prefix else rel, "mode": "100644", "type": "blob", "content": f.read_text(encoding="utf-8", errors="replace")})
        return out

    tree = await hass.async_add_executor_job(collect)
    if not tree:
        raise LibraryError("La bibliothèque locale est vide : exportez d’abord des packages.")

    async def call(method: str, path: str, payload: Any = None) -> tuple[int, Any]:
        async with session.request(method, f"{GH_API}/repos/{repo}{path}", headers=h, json=payload, timeout=ClientTimeout(total=120)) as r:
            try:
                body = await r.json()
            except Exception:  # noqa: BLE001
                body = None
            return r.status, body

    status, ref = await call("GET", f"/git/ref/heads/{branch}")
    if status in (404, 409):
        # empty repository: create the branch with a first file through the contents API
        import base64

        status, _ = await call("PUT", "/contents/" + (f"{prefix}/" if prefix else "") + ".bibliotheque-ha", {
            "message": "Initialisation de la bibliothèque HA", "branch": branch,
            "content": base64.b64encode(b"bibliotheque-ha\n").decode(),
        })
        if status not in (200, 201):
            raise LibraryError(f"Impossible d’initialiser le dépôt {repo} (code {status}).")
        status, ref = await call("GET", f"/git/ref/heads/{branch}")
    if status in (401, 403):
        raise LibraryError("Jeton GitHub refusé : il faut le droit « Contents: write » sur ce dépôt.")
    if status != 200:
        raise LibraryError(f"Branche {branch} introuvable sur {repo} (code {status}).")
    head = ref["object"]["sha"]
    status, commit = await call("GET", f"/git/commits/{head}")
    if status != 200:
        raise LibraryError("Lecture du dernier commit impossible.")
    status, new_tree = await call("POST", "/git/trees", {"base_tree": commit["tree"]["sha"], "tree": tree})
    if status != 201:
        raise LibraryError(f"Création de l’arborescence refusée par GitHub (code {status}).")
    status, new_commit = await call("POST", "/git/commits", {"message": message, "tree": new_tree["sha"], "parents": [head]})
    if status != 201:
        raise LibraryError(f"Création du commit refusée (code {status}).")
    status, _ = await call("PATCH", f"/git/refs/heads/{branch}", {"sha": new_commit["sha"]})
    if status != 200:
        raise LibraryError(f"Mise à jour de la branche refusée (code {status}).")
    return {"commit": new_commit["sha"], "files": len(tree), "url": f"https://github.com/{repo}/commit/{new_commit['sha']}"}
