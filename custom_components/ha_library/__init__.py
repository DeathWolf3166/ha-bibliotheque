"""Bibliothèque HA — scan, share and install reusable Home Assistant packages."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from . import analyzer, dashboards, installer, library, scanner, yamlutil
from .const import (
    DOMAIN, PANEL_COMPONENT, PANEL_URL, STATIC_URL, STORAGE_KEY, STORAGE_VERSION, VERSION,
)
from .library import LibraryError

_LOGGER = logging.getLogger(__name__)

DEFAULT_RULES = """# Règles de regroupement (optionnel)
# strip_prefixes: préfixes ignorés dans les noms (ex. un outil qui préfixe tout)
strip_prefixes: []
# groups: un package par règle ; « match » est une expression régulière testée sur
# l'identifiant et le nom (sans accents, espaces remplacés par _).
groups: []
#  - id: securite-prises
#    title: "Sécurité : remise en marche des prises critiques"
#    description: Remet à ON les prises qui ne doivent jamais rester coupées.
#    contexts: [particulier, hotel, logistique, bureau]
#    match: securite_repasser
"""


class Data:
    """Runtime data held in hass.data[DOMAIN]."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {}
        self.snapshot: dict | None = None
        self.analysis: dict | None = None

    async def load(self) -> None:
        self.data = await self.store.async_load() or {}
        s = self.data.setdefault("settings", {})
        s.setdefault("instance_name", self.entry.data.get("instance_name") or self.hass.config.location_name)
        s.setdefault("sources", [{"id": "local", "type": "local", "name": "Bibliothèque locale"}])
        s.setdefault("publish_to", None)
        s.setdefault("rules", DEFAULT_RULES)
        self.data.setdefault("overrides", {"packages": {}, "items": {}})
        self.data.setdefault("installed", {})
        self.data.setdefault("mappings", {})

    async def save(self) -> None:
        await self.store.async_save(self.data)

    def source(self, source_id: str) -> dict:
        for s in self.data["settings"]["sources"]:
            if s["id"] == source_id:
                return s
        raise LibraryError(f"Source « {source_id} » inconnue.")

    def root(self, source_id: str) -> Path:
        return library.source_root(self.hass, self.source(source_id))

    def rules(self) -> dict:
        try:
            r = yamlutil.load(self.data["settings"].get("rules") or "") or {}
            return r if isinstance(r, dict) else {}
        except Exception as err:  # noqa: BLE001
            raise LibraryError(f"Règles de regroupement invalides : {err}") from err

    def analyze(self) -> dict:
        assert self.snapshot is not None
        self.analysis = analyzer.analyze(self.snapshot, self.rules(), self.data["overrides"])
        return self.analysis


def _get(hass: HomeAssistant) -> Data:
    return hass.data[DOMAIN]


# ---------------------------------------------------------------- setup
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = Data(hass, entry)
    await data.load()
    hass.data[DOMAIN] = data

    if not hass.data.get(f"{DOMAIN}_static"):
        path = str(Path(__file__).parent / "frontend")
        try:
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, path, False)])
        except ImportError:  # HA < 2024.7
            hass.http.register_static_path(STATIC_URL, path, cache_headers=False)
        hass.data[f"{DOMAIN}_static"] = True
        for cmd in COMMANDS:
            websocket_api.async_register_command(hass, cmd)

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Bibliothèque",
        sidebar_icon="mdi:bookshelf",
        module_url=f"{STATIC_URL}/ha-library-panel.js?v={VERSION}",
        require_admin=True,
        config={"version": VERSION},
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL)
    hass.data.pop(DOMAIN, None)
    return True


# ---------------------------------------------------------------- websocket helpers
def _ws(schema: dict):
    """Decorator: admin-only async websocket command with French error messages."""

    def deco(fn):
        @websocket_api.websocket_command(schema)
        @websocket_api.require_admin
        @websocket_api.async_response
        async def handler(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
            if DOMAIN not in hass.data:
                connection.send_error(msg["id"], "not_loaded", "Bibliothèque HA n’est pas chargée.")
                return
            try:
                result = await fn(hass, _get(hass), msg)
            except LibraryError as err:
                connection.send_error(msg["id"], "library_error", str(err))
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Erreur %s", msg["type"])
                connection.send_error(msg["id"], "unknown_error", f"{type(err).__name__} : {err}")
                return
            connection.send_result(msg["id"], yamlutil.to_jsonable(result))

        handler.__name__ = fn.__name__
        return handler

    return deco


def _public_settings(d: Data) -> dict:
    s = dict(d.data["settings"])
    s["sources"] = [{k: v for k, v in src.items() if k != "token"} | {"has_token": bool(src.get("token"))} for src in s["sources"]]
    return s


def _summary(d: Data) -> dict:
    a, snap = d.analysis or {}, d.snapshot or {}
    return {
        "instance": snap.get("instance"),
        "packages": a.get("packages", []),
        "items": a.get("items", {}),
        "views": [{k: v for k, v in x.items() if k != "yaml"} | {"size": len(x["yaml"])} for x in snap.get("views", [])],
        "resources": snap.get("resources", []),
        "orphans": snap.get("orphans", []),
        "redactions": len(snap.get("redactions", [])),
        "generated_secrets": snap.get("generated_secrets", []),
        "overrides": d.data["overrides"],
    }


# ---------------------------------------------------------------- commands
@_ws({vol.Required("type"): "ha_library/settings/get"})
async def ws_settings_get(hass, d: Data, msg):
    return _public_settings(d) | {"installed": d.data["installed"]}


@_ws({
    vol.Required("type"): "ha_library/settings/set",
    vol.Optional("instance_name"): str,
    vol.Optional("rules"): str,
    vol.Optional("publish_to"): vol.Any(None, str),
    vol.Optional("source"): dict,          # add or update one source
    vol.Optional("remove_source"): str,
})
async def ws_settings_set(hass, d: Data, msg):
    s = d.data["settings"]
    if "instance_name" in msg:
        s["instance_name"] = msg["instance_name"].strip() or s["instance_name"]
    if "rules" in msg:
        try:
            r = yamlutil.load(msg["rules"])
            if r is not None and not isinstance(r, dict):
                raise ValueError("le document doit être un dictionnaire")
        except Exception as err:  # noqa: BLE001
            raise LibraryError(f"Règles invalides : {err}") from err
        s["rules"] = msg["rules"]
    if "publish_to" in msg:
        s["publish_to"] = msg["publish_to"]
    if src := msg.get("source"):
        repo = (src.get("repo") or "").strip().removeprefix("https://github.com/").strip("/")
        if repo.count("/") != 1:
            raise LibraryError("Indiquez le dépôt sous la forme propriétaire/nom (ex. maxime/bibliotheque-ha).")
        sid = f"gh:{repo}"
        existing = next((x for x in s["sources"] if x["id"] == sid), None)
        new = {"id": sid, "type": "github", "repo": repo, "branch": (src.get("branch") or "main").strip(),
               "path": (src.get("path") or "").strip("/"), "name": src.get("name") or repo}
        if src.get("token"):
            new["token"] = src["token"].strip()
        elif existing and existing.get("token"):
            new["token"] = existing["token"]
        if existing:
            existing.clear()
            existing.update(new)
        else:
            s["sources"].append(new)
    if rid := msg.get("remove_source"):
        if rid == "local":
            raise LibraryError("La bibliothèque locale ne peut pas être retirée.")
        s["sources"] = [x for x in s["sources"] if x["id"] != rid]
        if s.get("publish_to") == rid:
            s["publish_to"] = None
    await d.save()
    return _public_settings(d)


@_ws({vol.Required("type"): "ha_library/scan"})
async def ws_scan(hass, d: Data, msg):
    d.snapshot = await scanner.async_scan(hass, d.data["settings"]["instance_name"])
    await hass.async_add_executor_job(d.analyze)
    return _summary(d)


@_ws({vol.Required("type"): "ha_library/scan/result"})
async def ws_scan_result(hass, d: Data, msg):
    return _summary(d) if d.snapshot else None


@_ws({
    vol.Required("type"): "ha_library/override",
    vol.Optional("package_id"): str,
    vol.Optional("title"): str,
    vol.Optional("description"): str,
    vol.Optional("contexts"): [str],
    vol.Optional("exclude"): bool,
    vol.Optional("item_uid"): str,
    vol.Optional("move_to"): vol.Any(None, str),
})
async def ws_override(hass, d: Data, msg):
    ov = d.data["overrides"]
    if uid := msg.get("item_uid"):
        target = msg.get("move_to")
        if target:
            ov["items"][uid] = analyzer.slugify(target).replace("_", "-")
        else:
            ov["items"].pop(uid, None)
    if pid := msg.get("package_id"):
        po = ov["packages"].setdefault(pid, {})
        for k in ("title", "description", "contexts", "exclude"):
            if k in msg:
                po[k] = msg[k]
    await d.save()
    if not d.snapshot:
        raise LibraryError("Lancez d’abord un scan.")
    await hass.async_add_executor_job(d.analyze)
    return _summary(d)


@_ws({vol.Required("type"): "ha_library/export", vol.Required("package_ids"): [str]})
async def ws_export(hass, d: Data, msg):
    if not d.analysis:
        raise LibraryError("Lancez d’abord un scan.")
    root = d.root("local")
    return await hass.async_add_executor_job(library.write_export, root, d.analysis, d.snapshot, msg["package_ids"])


@_ws({vol.Required("type"): "ha_library/publish", vol.Required("source_id"): str, vol.Optional("message"): str})
async def ws_publish(hass, d: Data, msg):
    src = d.source(msg["source_id"])
    if src["type"] != "github":
        raise LibraryError("La publication se fait vers un dépôt GitHub.")
    msg_txt = msg.get("message") or f"Bibliothèque HA : export de {d.data['settings']['instance_name']}"
    return await library.async_publish_github(hass, d.root("local"), src, msg_txt)


@_ws({vol.Required("type"): "ha_library/source/refresh", vol.Required("source_id"): str})
async def ws_refresh(hass, d: Data, msg):
    src = d.source(msg["source_id"])
    if src["type"] != "github":
        return {"files": 0}
    res = await library.async_fetch_github(hass, src)
    src["fetched_at"] = res["fetched_at"]
    await d.save()
    return res


@_ws({vol.Required("type"): "ha_library/library", vol.Required("source_id"): str})
async def ws_library(hass, d: Data, msg):
    root = d.root(msg["source_id"])
    idx = await hass.async_add_executor_job(library.read_library, root)
    inst = d.data["installed"]
    for p in idx["packages"]:
        rec = inst.get(p["id"])
        p["installed"] = None if not rec else {"version": rec["version"], "update": rec["version"] != p.get("version"), "installed_at": rec["installed_at"]}
    return idx


@_ws({vol.Required("type"): "ha_library/package", vol.Required("source_id"): str, vol.Required("package_id"): str})
async def ws_package(hass, d: Data, msg):
    return await hass.async_add_executor_job(library.read_package, d.root(msg["source_id"]), msg["package_id"])


@_ws({vol.Required("type"): "ha_library/view", vol.Required("source_id"): str, vol.Required("view_id"): str})
async def ws_view(hass, d: Data, msg):
    return {"yaml": await hass.async_add_executor_job(library.read_view, d.root(msg["source_id"]), msg["view_id"])}


@_ws({vol.Required("type"): "ha_library/library/remove", vol.Required("package_id"): str})
async def ws_lib_remove(hass, d: Data, msg):
    await hass.async_add_executor_job(library.remove_package, d.root("local"), msg["package_id"])
    return {"removed": msg["package_id"]}


def _merged_mapping(d: Data, mapping: dict | None) -> dict:
    m = dict(d.data["mappings"])
    for k, v in (mapping or {}).items():
        if v:
            m[k] = v
        else:
            m.pop(k, None)
    return m


@_ws({
    vol.Required("type"): "ha_library/plan", vol.Required("source_id"): str,
    vol.Required("package_ids"): [str], vol.Optional("mapping"): dict,
})
async def ws_plan(hass, d: Data, msg):
    mapping = _merged_mapping(d, msg.get("mapping"))
    plan = await installer.async_plan(hass, d.root(msg["source_id"]), msg["package_ids"], mapping, d.data["installed"])
    return plan


@_ws({
    vol.Required("type"): "ha_library/install", vol.Required("source_id"): str,
    vol.Required("package_ids"): [str], vol.Optional("mapping"): dict, vol.Optional("secrets"): dict,
    vol.Optional("enable_packages", default=False): bool, vol.Optional("force_update", default=False): bool,
})
async def ws_install(hass, d: Data, msg):
    mapping = _merged_mapping(d, msg.get("mapping"))
    res = await installer.async_install(
        hass, d.root(msg["source_id"]), msg["package_ids"], mapping, msg.get("secrets") or {},
        d.data["installed"], enable=msg["enable_packages"], force_update=msg["force_update"],
    )
    for pid, rec in res["records"].items():
        rec["source"] = msg["source_id"]
        d.data["installed"][pid] = rec
    d.data["mappings"] = mapping
    await d.save()
    return res


@_ws({vol.Required("type"): "ha_library/uninstall", vol.Required("package_id"): str, vol.Optional("force", default=False): bool})
async def ws_uninstall(hass, d: Data, msg):
    res = await installer.async_uninstall(hass, msg["package_id"], d.data["installed"], msg["force"])
    d.data["installed"].pop(msg["package_id"], None)
    await d.save()
    return res


@_ws({vol.Required("type"): "ha_library/dashboards"})
async def ws_dashboards(hass, d: Data, msg):
    return dashboards.list_dashboards(hass)


@_ws({
    vol.Required("type"): "ha_library/view/install", vol.Required("source_id"): str,
    vol.Required("view_id"): str, vol.Required("dashboard"): str, vol.Optional("mapping"): dict,
})
async def ws_view_install(hass, d: Data, msg):
    yaml_text = await hass.async_add_executor_job(library.read_view, d.root(msg["source_id"]), msg["view_id"])
    return await dashboards.async_install_view(hass, yaml_text, msg["dashboard"], _merged_mapping(d, msg.get("mapping")))


@_ws({vol.Required("type"): "ha_library/ghosts"})
async def ws_ghosts(hass, d: Data, msg):
    return dashboards.ghost_entries(hass)


@_ws({vol.Required("type"): "ha_library/ghosts/remove", vol.Required("entity_ids"): [str]})
async def ws_ghosts_remove(hass, d: Data, msg):
    return {"removed": dashboards.remove_ghosts(hass, msg["entity_ids"])}


COMMANDS = [
    ws_settings_get, ws_settings_set, ws_scan, ws_scan_result, ws_override, ws_export, ws_publish,
    ws_refresh, ws_library, ws_package, ws_view, ws_lib_remove, ws_plan, ws_install, ws_uninstall,
    ws_dashboards, ws_view_install, ws_ghosts, ws_ghosts_remove,
]
