"""Read everything reusable from the running Home Assistant instance.

Produces a *snapshot* consumed by analyzer.analyze(). Sources:
- automations / scripts: the loaded entities' raw_config (UI, YAML and packages)
- scenes, templates, legacy platforms, keyed YAML domains: the merged configuration
  (configuration.yaml + includes + packages), re-read from disk
- helpers: YAML definitions + .storage collections
- UI template helpers: config entries
- pyscript, python_scripts, blueprints: files under /config
- dashboards and front-end resources: .storage/lovelace*
Secret values found anywhere are turned back into `!secret name`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import yamlutil
from .analyzer import HELPER_DOMAINS, ENT_RX
from .yamlutil import SecretRef, slugify

_LOGGER = logging.getLogger(__name__)

TEMPLATE_PLATFORMS = (
    "sensor", "binary_sensor", "number", "select", "button", "image", "weather", "switch", "light",
    "fan", "cover", "lock", "alarm_control_panel", "vacuum", "event", "update",
)
PLATFORM_DOMAINS = (
    "sensor", "binary_sensor", "switch", "light", "cover", "fan", "climate", "media_player",
    "notify", "camera", "device_tracker", "lock", "weather", "tts", "vacuum",
)
KEYED_DOMAINS = {"utility_meter", "shell_command", "rest_command", "group", "alert", "proximity", "plant"}
LIST_DOMAINS = {"command_line", "rest", "scrape", "sql"}
SKIP_PLATFORMS = {"template"}  # legacy template handled per entity

PHONE_RX = re.compile(r"^(?:\+\d{1,3}[ .]?\d(?:[ .]?\d{2}){4}|\+\d{9,14}|0[1-9](?:[ .]?\d{2}){4})$")
NEVER_REDACT = {"id", "unique_id", "alias", "name", "friendly_name", "entity_id", "device_id", "platform", "at", "offset", "for", "icon", "mode", "trigger", "action", "service", "condition", "state", "to", "from"}
EMAIL_RX = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$")
SECRET_KEYS = {"webhook_id", "api_key", "token", "access_token", "password", "secret", "auth_token", "client_secret", "username"}


def _domain_keys(conf: dict, domain: str) -> list[str]:
    rx = re.compile(rf"^{re.escape(domain)}(\s.*)?$")
    return [k for k in conf if isinstance(k, str) and rx.match(k)]


class _Redactor:
    def __init__(self, secrets: dict[str, Any]) -> None:
        self.by_value: dict[str, str] = {}
        for k, v in (secrets or {}).items():
            if isinstance(v, (str, int, float)) and len(str(v)) >= 4:
                self.by_value[str(v)] = k
        self.generated: dict[str, str] = {}  # generated name -> kind
        self.hits: list[dict] = []

    def _gen(self, base: str) -> SecretRef:
        name = slugify(base)[:60]
        n, i = name, 2
        while n in self.generated and self.generated[n] != base:
            n = f"{name}_{i}"
            i += 1
        self.generated[n] = base
        return SecretRef(n)

    def __call__(self, obj: Any, where: str, key: str | None = None) -> Any:
        if isinstance(obj, SecretRef):
            return obj
        if isinstance(obj, dict):
            return {k: self(v, where, str(k)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self(v, where, key) for v in obj]
        if key in NEVER_REDACT:
            return obj
        if isinstance(obj, (str, int)) and not isinstance(obj, bool):
            s = str(obj)
            if s in self.by_value:
                self.hits.append({"where": where, "secret": self.by_value[s]})
                return SecretRef(self.by_value[s])
            if isinstance(obj, str):
                for val, name in self.by_value.items():
                    if len(val) >= 8 and val in s:
                        self.hits.append({"where": where, "secret": name + "_texte"})
                        return SecretRef(name + "_texte")
                if key in SECRET_KEYS and s and "{{" not in s:
                    self.hits.append({"where": where, "secret": key})
                    return self._gen(f"{where.split('.')[-1]}_{key}")
                if (PHONE_RX.match(s.strip()) and not s.strip().isdigit() or s.strip().startswith("0") and PHONE_RX.match(s.strip())) or EMAIL_RX.match(s.strip()):
                    self.hits.append({"where": where, "secret": "contact"})
                    return self._gen(f"{where.split('.')[-1]}_{'telephone' if PHONE_RX.match(s.strip()) else 'email'}")
        return obj

    def text(self, content: str, where: str) -> tuple[str, list[str]]:
        found = []
        for val, name in self.by_value.items():
            if len(val) >= 6 and val in content:
                content = content.replace(val, f"<SECRET:{name}>")
                found.append(name)
        if found:
            self.hits.append({"where": where, "secret": ",".join(found)})
        return content, found


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_secrets(config_dir: Path) -> dict:
    p = config_dir / "secrets.yaml"
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _plain(o: Any) -> Any:
    """Turn HA objects (Template, timedelta, NodeStrClass…) into YAML-able values."""
    if isinstance(o, SecretRef):
        return o
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, bool) or o is None or isinstance(o, (int, float)):
        return o
    if hasattr(o, "template") and isinstance(getattr(o, "template"), str):
        return o.template
    if isinstance(o, str):
        return str(o)
    return str(o)


def _files_scan(config_dir: Path, red: _Redactor) -> list[dict]:
    items = []
    # pyscript
    for base in ("pyscript",):
        root = config_dir / base
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*.py")):
            rel = f.relative_to(config_dir).as_posix()
            if "/__pycache__/" in rel:
                continue
            content = f.read_text(encoding="utf-8", errors="replace")
            content, found = red.text(content, rel)
            funcs = re.findall(r"@service[^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:async\s+)?def\s+(\w+)", content)
            items.append({
                "uid": f"file:{rel}", "kind": "file", "domain": "pyscript", "key": rel,
                "name": f"pyscript · {f.stem}", "description": f"{len(funcs)} service(s) : {', '.join(funcs)}" if funcs else "",
                "config": content, "file": {"path": rel, "content": content, "secrets_removed": found},
                "provides": [f"pyscript.{fn}" for fn in funcs] + [f"file:{rel}"], "integrations": ["pyscript"],
            })
    # python_scripts
    root = config_dir / "python_scripts"
    if root.is_dir():
        for f in sorted(root.glob("*.py")):
            rel = f.relative_to(config_dir).as_posix()
            content, found = red.text(f.read_text(encoding="utf-8", errors="replace"), rel)
            items.append({
                "uid": f"file:{rel}", "kind": "file", "domain": "python_script", "key": rel,
                "name": f"python_script · {f.stem}", "description": "", "config": content,
                "file": {"path": rel, "content": content, "secrets_removed": found},
                "provides": [f"python_script.{f.stem}"], "integrations": ["python_script"],
            })
    # blueprints
    for dom in ("automation", "script", "template"):
        root = config_dir / "blueprints" / dom
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*.yaml")):
            rel = f.relative_to(config_dir).as_posix()
            bp_path = f.relative_to(root).as_posix()
            content = f.read_text(encoding="utf-8", errors="replace")
            name = bp_path
            m = re.search(r"^\s*name:\s*(.+)$", content, re.M)
            if m:
                name = m.group(1).strip().strip("'\"")
            items.append({
                "uid": f"file:{rel}", "kind": "file", "domain": f"blueprint_{dom}", "key": rel,
                "name": f"Blueprint · {name}", "description": bp_path, "config": None,
                "file": {"path": rel, "content": content, "secrets_removed": []},
                "provides": [f"blueprint:{bp_path}"],
            })
    return items


def _lovelace(config_dir: Path, red: _Redactor) -> tuple[list[dict], list[dict]]:
    storage = config_dir / ".storage"
    views: list[dict] = []
    dashes = [("lovelace", "Aperçu", storage / "lovelace")]
    dl = _read_json(storage / "lovelace_dashboards") or {}
    for d in (dl.get("data") or {}).get("items", []):
        if d.get("mode", "storage") != "storage":
            continue
        dashes.append((d.get("url_path") or d["id"], d.get("title") or d.get("url_path"), storage / f"lovelace.{d['id']}"))
    for url, title, path in dashes:
        if re.match(r"^(backup|test)-", url or ""):
            continue
        data = _read_json(path)
        cfg = ((data or {}).get("data") or {}).get("config") or {}
        for idx, v in enumerate(cfg.get("views") or []):
            v = red(v, f"lovelace.{url}")
            txt = json.dumps(yamlutil.to_jsonable(v))
            vt = v.get("title") or v.get("path") or f"vue {idx + 1}"
            views.append({
                "id": slugify(f"{url}-{v.get('path') or idx}").replace("_", "-"),
                "dashboard": title, "dashboard_path": url, "title": vt,
                "custom_cards": sorted(set(re.findall(r"custom:([a-z0-9\-_]+)", txt))),
                "entities": len(set(m.group(0) for m in ENT_RX.finditer(txt))),
                "yaml": yamlutil.dump(v),
            })
    res = _read_json(storage / "lovelace_resources") or {}
    resources = []
    for r in (res.get("data") or {}).get("items", []):
        u = r.get("url", "")
        m = re.search(r"/hacsfiles/([^/]+)/", u)
        resources.append({"url": re.sub(r"\?.*", "", u), "repo": m.group(1) if m else None, "type": r.get("res_type")})
    return views, resources


async def async_scan(hass: HomeAssistant, instance_name: str | None = None) -> dict:
    config_dir = Path(hass.config.config_dir)
    secrets = await hass.async_add_executor_job(_read_secrets, config_dir)
    red = _Redactor(secrets)

    try:
        from homeassistant import config as conf_util

        conf = await conf_util.async_hass_config_yaml(hass)
    except Exception as err:  # noqa: BLE001 - keep scanning without YAML
        _LOGGER.warning("Lecture de la configuration YAML impossible : %s", err)
        conf = {}

    reg = er.async_get(hass)
    entities: dict[str, dict] = {}
    for e in reg.entities.values():
        entities[e.entity_id] = {"platform": e.platform, "unique_id": e.unique_id, "config_entry_id": e.config_entry_id}
    for s in hass.states.async_all():
        entities.setdefault(s.entity_id, {"platform": None})

    def by_unique(platform: str, domain: str, uid: str) -> str | None:
        eid = reg.async_get_entity_id(domain, platform, uid)
        if eid:
            return eid
        for e in reg.entities.values():
            if e.platform == platform and e.domain == domain and str(e.unique_id).endswith(str(uid)):
                return e.entity_id
        return None

    # categories (HA ≥ 2024.4)
    def category_name(entity_id: str, scope: str) -> str | None:
        try:
            from homeassistant.helpers import category_registry as cr

            ent = reg.async_get(entity_id)
            if not ent or not ent.categories.get(scope):
                return None
            cat = cr.async_get(hass).async_get_category(scope=scope, category_id=ent.categories[scope])
            return cat.name if cat else None
        except Exception:  # noqa: BLE001
            return None

    items: list[dict] = []

    # ---- automations
    comp = hass.data.get("automation")
    seen_auto = set()
    for ent in list(getattr(comp, "entities", []) or []):
        raw = getattr(ent, "_blueprint_inputs", None) or getattr(ent, "raw_config", None)
        if not raw:
            continue
        raw = _plain(dict(raw))
        key = str(raw.get("id") or ent.entity_id.split(".", 1)[1])
        seen_auto.add(key)
        st = hass.states.get(ent.entity_id)
        items.append({
            "uid": f"automation:{key}", "kind": "automation", "domain": "automation", "key": key,
            "name": raw.get("alias") or ent.entity_id, "description": raw.get("description") or "",
            "config": red(raw, ent.entity_id), "provides": [ent.entity_id],
            "emit": {"section": "automation", "mode": "list"},
            "category": category_name(ent.entity_id, "automation"),
            "enabled": not (st and st.state == "off"),
        })

    # ---- scripts
    comp = hass.data.get("script")
    for ent in list(getattr(comp, "entities", []) or []):
        raw = getattr(ent, "_blueprint_inputs", None) or getattr(ent, "raw_config", None)
        if raw is None:
            continue
        key = ent.entity_id.split(".", 1)[1]
        raw = _plain(dict(raw))
        items.append({
            "uid": f"script:{key}", "kind": "script", "domain": "script", "key": key,
            "name": raw.get("alias") or key, "description": raw.get("description") or "",
            "config": red(raw, ent.entity_id), "provides": [ent.entity_id],
            "emit": {"section": "script", "mode": "dict", "key": key},
            "category": category_name(ent.entity_id, "script"),
        })

    # ---- scenes
    for k in _domain_keys(conf, "scene"):
        for sc in conf.get(k) or []:
            if not isinstance(sc, dict) or sc.get("platform"):
                continue
            sc = _plain(sc)
            sid = str(sc.get("id") or slugify(sc.get("name", "scene")))
            eid = by_unique("homeassistant", "scene", sid) or f"scene.{slugify(sc.get('name', sid))}"
            items.append({
                "uid": f"scene:{sid}", "kind": "scene", "domain": "scene", "key": sid,
                "name": sc.get("name") or sid, "description": "", "config": red(sc, eid),
                "provides": [eid], "emit": {"section": "scene", "mode": "list"},
            })

    # ---- helpers (YAML + storage)
    storage = config_dir / ".storage"
    for dom in sorted(HELPER_DOMAINS):
        defs: dict[str, dict] = {}
        for k in _domain_keys(conf, dom):
            for key, cfg in (conf.get(k) or {}).items():
                defs[str(key)] = _plain(cfg or {})
        data = await hass.async_add_executor_job(_read_json, storage / dom)
        for it in ((data or {}).get("data") or {}).get("items", []):
            it = dict(it)
            key = str(it.pop("id"))
            defs.setdefault(key, it)
        for key, cfg in defs.items():
            eid = f"{dom}.{key}"
            items.append({
                "uid": f"helper:{eid}", "kind": "helper", "domain": dom, "key": key,
                "name": (cfg or {}).get("name") or key, "description": "", "config": red(cfg, eid),
                "provides": [eid], "emit": {"section": dom, "mode": "dict", "key": key},
            })

    # ---- modern template
    for k in _domain_keys(conf, "template"):
        blocks = conf.get(k) or []
        if isinstance(blocks, dict):
            blocks = [blocks]
        for bi, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            block = _plain(block)
            buid = block.get("unique_id")
            if block.get("trigger") or block.get("triggers"):
                provides = []
                names = []
                for plat in TEMPLATE_PLATFORMS:
                    for ec in block.get(plat) or []:
                        uid_ = ec.get("unique_id")
                        full = f"{buid}-{uid_}" if buid and uid_ else uid_
                        eid = (by_unique("template", plat, full) if full else None) or f"{plat}.{slugify(ec.get('name', 'template'))}"
                        provides.append(eid)
                        names.append(str(ec.get("name", eid)))
                key = slugify("trigger_" + "_".join(names[:2]))
                items.append({
                    "uid": f"template:{key}:{bi}", "kind": "template", "domain": "template", "key": key,
                    "name": "Template à déclencheur · " + ", ".join(names[:3]), "description": "",
                    "config": red(block, key), "provides": provides, "emit": {"section": "template", "mode": "list"},
                })
                continue
            for plat in TEMPLATE_PLATFORMS:
                for ec in block.get(plat) or []:
                    uid_ = ec.get("unique_id")
                    full = f"{buid}-{uid_}" if buid and uid_ else uid_
                    eid = (by_unique("template", plat, full) if full else None) or f"{plat}.{slugify(ec.get('name', 'template'))}"
                    single = {kk: vv for kk, vv in block.items() if kk not in TEMPLATE_PLATFORMS}
                    single[plat] = [ec]
                    items.append({
                        "uid": f"template:{eid}", "kind": "template", "domain": "template", "key": eid,
                        "name": str(ec.get("name") or eid), "description": "",
                        "config": red(single, eid), "provides": [eid], "emit": {"section": "template", "mode": "list"},
                    })

    # ---- UI template helpers → YAML template
    for entry in hass.config_entries.async_entries("template"):
        opts = dict(entry.options)
        ttype = opts.pop("template_type", None)
        if not ttype:
            continue
        eid = next((e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)), f"{ttype}.{slugify(opts.get('name', entry.title))}")
        cfg = {kk: vv for kk, vv in opts.items() if kk in ("name", "state", "unit_of_measurement", "device_class", "state_class", "icon", "availability", "attributes")}
        cfg["unique_id"] = entry.entry_id
        items.append({
            "uid": f"template:{eid}", "kind": "template", "domain": "template", "key": eid,
            "name": str(opts.get("name") or entry.title), "description": "Helper template créé dans l’interface",
            "config": red({ttype: [cfg]}, eid), "provides": [eid], "emit": {"section": "template", "mode": "list"},
        })

    # ---- legacy platform domains (sensor: - platform: …)
    for dom in PLATFORM_DOMAINS:
        for k in _domain_keys(conf, dom):
            for idx, ec in enumerate(conf.get(k) or []):
                if not isinstance(ec, dict):
                    continue
                ec = _plain(ec)
                plat = ec.get("platform", "?")
                if plat == "template":
                    for sk, sc in (ec.get("sensors") or ec.get("switches") or ec.get("covers") or ec.get("lights") or {}).items():
                        eid = f"{dom}.{sk}"
                        sub = "sensors" if "sensors" in ec else next(x for x in ("switches", "covers", "lights") if x in ec)
                        items.append({
                            "uid": f"yaml:{eid}", "kind": "template", "domain": dom, "key": eid,
                            "name": str(sc.get("friendly_name") or sk), "description": "Template ancien format",
                            "config": red({"platform": "template", sub: {sk: sc}}, eid), "provides": [eid],
                            "emit": {"section": dom, "mode": "list"},
                        })
                    continue
                name = ec.get("name") or f"{plat}_{idx}"
                eid = f"{dom}.{slugify(name)}"
                if ec.get("unique_id"):
                    eid = by_unique(plat, dom, ec["unique_id"]) or eid
                items.append({
                    "uid": f"yaml:{dom}:{plat}:{slugify(name)}", "kind": "yaml", "domain": dom, "key": eid,
                    "name": f"{dom} · {plat} · {name}", "description": "", "config": red(ec, eid),
                    "provides": [eid], "emit": {"section": dom, "mode": "list"}, "integrations": [plat],
                })

    # ---- keyed YAML domains
    for dom in sorted(KEYED_DOMAINS):
        for k in _domain_keys(conf, dom):
            for key, cfg in (conf.get(k) or {}).items():
                cfg = _plain(cfg)
                key = str(key)
                if dom == "utility_meter":
                    prov = [f"sensor.{key}"]
                    for t in (cfg or {}).get("tariffs") or []:
                        prov += [f"select.{key}", f"sensor.{key}_{slugify(t)}"]
                elif dom in ("shell_command", "rest_command"):
                    prov = [f"{dom}.{key}"]
                else:
                    prov = [f"{dom}.{key}"]
                items.append({
                    "uid": f"yaml:{dom}:{key}", "kind": "yaml", "domain": dom, "key": key,
                    "name": f"{dom} · {key}", "description": "", "config": red(cfg, f"{dom}.{key}"),
                    "provides": sorted(set(prov)), "emit": {"section": dom, "mode": "dict", "key": key},
                    "integrations": [dom],
                })
    for dom in sorted(LIST_DOMAINS):
        for k in _domain_keys(conf, dom):
            for idx, ec in enumerate(conf.get(k) or []):
                ec = _plain(ec)
                inner = next(iter(ec.values()), {}) if isinstance(ec, dict) and len(ec) == 1 else ec
                pdom = next(iter(ec)) if isinstance(ec, dict) and len(ec) == 1 else "sensor"
                name = (inner or {}).get("name", f"{dom}_{idx}") if isinstance(inner, dict) else f"{dom}_{idx}"
                eid = f"{pdom}.{slugify(name)}"
                items.append({
                    "uid": f"yaml:{dom}:{slugify(name)}", "kind": "yaml", "domain": dom, "key": eid,
                    "name": f"{dom} · {name}", "description": "", "config": red(ec, eid),
                    "provides": [eid], "emit": {"section": dom, "mode": "list"}, "integrations": [dom],
                })

    # ---- files
    items += await hass.async_add_executor_job(_files_scan, config_dir, red)
    views, resources = await hass.async_add_executor_job(_lovelace, config_dir, red)

    # ---- device triggers: registry ids (uuid) → readable entity_id, and device descriptions
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    uuid_rx = re.compile(r"^[0-9a-f]{32}$")

    def fix_uuids(o: Any) -> Any:
        if isinstance(o, dict):
            out = {k: fix_uuids(v) for k, v in o.items()}
            eid = out.get("entity_id")
            if "device_id" in out and isinstance(eid, str) and uuid_rx.match(eid):
                resolved = er.async_resolve_entity_id(reg, eid)
                if resolved:
                    out["entity_id"] = resolved
            return out
        if isinstance(o, list):
            return [fix_uuids(v) for v in o]
        return o

    for it in items:
        if it.get("config") is not None and not it.get("file"):
            it["config"] = fix_uuids(it["config"])

    devices: dict[str, dict] = {}
    for dev in dev_reg.devices.values():
        domains = sorted({ce.domain for ce_id in dev.config_entries if (ce := hass.config_entries.async_get_entry(ce_id))})
        devices[dev.id] = {
            "name": dev.name_by_user or dev.name or dev.id, "manufacturer": dev.manufacturer, "model": dev.model,
            "integrations": domains,
        }

    # ---- dedupe uids
    seen: dict[str, int] = {}
    for it in items:
        u = it["uid"]
        if u in seen:
            seen[u] += 1
            it["uid"] = f"{u}#{seen[u]}"
        else:
            seen[u] = 1

    orphans = []
    for e in reg.entities.values():
        if e.domain in ("automation", "script") and e.disabled_by is None:
            st = hass.states.get(e.entity_id)
            if st is None or st.attributes.get("restored"):
                orphans.append(e.entity_id)

    integrations = sorted({e.domain for e in hass.config_entries.async_entries()} | {c.split(".")[0] for c in hass.config.components})
    name = instance_name or hass.config.location_name or "Instance"
    return {
        "format": 1,
        "instance": {
            "name": name, "slug": slugify(name), "ha_version": HA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entity_count": len(hass.states.async_entity_ids()),
        },
        "items": items, "entities": entities, "integrations": integrations, "devices": devices,
        "views": views, "resources": resources, "orphans": sorted(orphans),
        "redactions": red.hits, "generated_secrets": sorted(red.generated),
    }
