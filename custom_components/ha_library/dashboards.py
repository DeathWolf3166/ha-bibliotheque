"""Add a library view to a dashboard, and clean up ghost registry entries."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import yamlutil
from .analyzer import ENT_RX
from .const import LOCAL_DIR
from .installer import apply_mapping
from .library import LibraryError


def _dashboards(hass: HomeAssistant) -> dict:
    ld = hass.data.get("lovelace")
    dashes = getattr(ld, "dashboards", None)
    if dashes is None and isinstance(ld, dict):
        dashes = ld.get("dashboards")
    return dashes or {}


def list_dashboards(hass: HomeAssistant) -> list[dict]:
    out = []
    for url, dash in _dashboards(hass).items():
        cfg = getattr(dash, "config", None) or {}
        out.append({
            "url_path": url or "lovelace",
            "title": cfg.get("title") or ("Aperçu" if url is None else url),
            "mode": getattr(dash, "mode", "?"),
        })
    return sorted(out, key=lambda d: (d["url_path"] != "lovelace", d["title"].lower()))


def _resource_urls(hass: HomeAssistant) -> list[str]:
    ld = hass.data.get("lovelace")
    res = getattr(ld, "resources", None)
    if res is None and isinstance(ld, dict):
        res = ld.get("resources")
    try:
        return [str(r.get("url", "")) for r in res.async_items()]
    except Exception:  # noqa: BLE001
        return []


def _card_installed(card: str, urls: list[str]) -> bool:
    key = card.replace("-card", "")
    return any(key in u.lower() or card in u.lower() for u in urls)


async def async_install_view(hass: HomeAssistant, view_yaml: str, url_path: str, mapping: dict) -> dict:
    dashes = _dashboards(hass)
    key = None if url_path == "lovelace" else url_path
    dash = dashes.get(key)
    if dash is None:
        raise LibraryError(f"Dashboard « {url_path} » introuvable.")
    if getattr(dash, "mode", "") != "storage":
        raise LibraryError("Ce dashboard est géré en YAML : collez la vue vous-même dans son fichier.")
    view = yamlutil.load(apply_mapping(view_yaml, mapping or {}))
    if not isinstance(view, dict):
        raise LibraryError("La vue de la bibliothèque est invalide.")
    view = yamlutil.from_jsonable(yamlutil.to_jsonable(view))
    try:
        config = await dash.async_load(False)
    except Exception:  # noqa: BLE001 - empty / auto-generated dashboard
        config = {"views": []}
    config = json.loads(json.dumps(config))  # detach from the stored object

    # backup before any change
    backup_dir = Path(hass.config.path(LOCAL_DIR, "backups"))

    def backup() -> str:
        backup_dir.mkdir(parents=True, exist_ok=True)
        p = backup_dir / f"lovelace-{url_path}-{datetime.now():%Y%m%d-%H%M%S}.json"
        p.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
        return p.relative_to(Path(hass.config.config_dir)).as_posix()

    backup_file = await hass.async_add_executor_job(backup)

    views = config.setdefault("views", [])
    paths = {v.get("path") for v in views if isinstance(v, dict)}
    base = view.get("path") or yamlutil.slugify(view.get("title", "vue")).replace("_", "-")
    path, n = base, 2
    while path in paths:
        path = f"{base}-{n}"
        n += 1
    view["path"] = path
    views.append(view)
    await dash.async_save(config)

    txt = json.dumps(yamlutil.to_jsonable(view))
    ents = sorted({m.group(0) for m in ENT_RX.finditer(txt)})
    missing = [e for e in ents if hass.states.get(e) is None]
    urls = _resource_urls(hass)
    cards = sorted(set(re.findall(r"custom:([a-z0-9\-_]+)", txt)))
    return {
        "dashboard": url_path, "path": path, "backup": backup_file,
        "missing_entities": missing, "missing_cards": [c for c in cards if not _card_installed(c, urls)],
    }


# ---------------------------------------------------------------- ghost entries
def ghost_entries(hass: HomeAssistant) -> list[dict]:
    reg = er.async_get(hass)
    out = []
    for e in reg.entities.values():
        if e.domain not in ("automation", "script", "scene"):
            continue
        if e.disabled_by is not None:  # deliberately disabled by the user: never a ghost
            continue
        st = hass.states.get(e.entity_id)
        if st is not None and not st.attributes.get("restored"):
            continue
        out.append({
            "entity_id": e.entity_id,
            "name": e.name or e.original_name or (st.attributes.get("friendly_name") if st else None) or e.entity_id,
            "unique_id": e.unique_id,
        })
    return sorted(out, key=lambda x: x["entity_id"])


def remove_ghosts(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    reg = er.async_get(hass)
    allowed = {g["entity_id"] for g in ghost_entries(hass)}
    removed = []
    for eid in entity_ids:
        if eid in allowed and reg.async_get(eid):
            reg.async_remove(eid)
            removed.append(eid)
    return removed
