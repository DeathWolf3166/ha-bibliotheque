"""Install library packages on this instance.

Steps: resolve dependencies → check integrations, entities, secrets, conflicts →
write /config/<packages>/bibliotheque/bibliotheque_<id>.yaml (+ shipped files) →
check the configuration → reload the touched domains, or roll everything back.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import IntegrationNotFound, async_get_integration

from . import library, yamlutil
from .const import INSTALL_SUBDIR
from .library import LibraryError

_LOGGER = logging.getLogger(__name__)

RELOADABLE = {
    "automation", "script", "scene", "template", "input_boolean", "input_number", "input_select",
    "input_text", "input_datetime", "input_button", "timer", "counter", "schedule", "group",
    "pyscript", "python_script", "command_line", "rest", "rest_command", "alert", "person", "zone",
}
HELPER_SECTIONS = {"input_boolean", "input_number", "input_select", "input_text", "input_datetime", "input_button", "timer", "counter", "schedule"}
PKG_LINE = "  packages: !include_dir_named packages\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- configuration.yaml / packages
def packages_setup(config_dir: Path) -> dict:
    conf_path = config_dir / "configuration.yaml"
    try:
        conf = yamlutil.load(conf_path.read_text(encoding="utf-8")) or {}
    except Exception as err:  # noqa: BLE001
        return {"enabled": False, "editable": False, "dir": None, "reason": f"configuration.yaml illisible : {err}"}
    ha = conf.get("homeassistant")
    if isinstance(ha, yamlutil.TaggedValue):
        if ha.tag == "!include":
            try:
                ha = yamlutil.load((config_dir / str(ha.value)).read_text(encoding="utf-8")) or {}
            except OSError:
                ha = {}
            pk = ha.get("packages") if isinstance(ha, dict) else None
            if isinstance(pk, yamlutil.TaggedValue) and pk.tag in ("!include_dir_named", "!include_dir_merge_named"):
                return {"enabled": True, "editable": False, "dir": str(pk.value), "reason": ""}
        return {"enabled": False, "editable": False, "dir": None, "reason": "La section homeassistant: est dans un fichier inclus : ajoutez « packages: !include_dir_named packages » vous-même."}
    if isinstance(ha, dict) and "packages" in ha:
        pk = ha["packages"]
        if isinstance(pk, yamlutil.TaggedValue) and pk.tag in ("!include_dir_named", "!include_dir_merge_named"):
            return {"enabled": True, "editable": False, "dir": str(pk.value), "reason": ""}
        return {"enabled": False, "editable": False, "dir": None, "reason": "Les packages sont déclarés autrement qu’avec un dossier (!include_dir_named) : la bibliothèque ne peut pas y écrire."}
    return {"enabled": False, "editable": True, "dir": None, "reason": "Les packages ne sont pas activés dans configuration.yaml."}


def enable_packages(config_dir: Path) -> Path:
    conf_path = config_dir / "configuration.yaml"
    text = conf_path.read_text(encoding="utf-8")
    backup = conf_path.with_name(f"configuration.yaml.bak-bibliotheque-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(conf_path, backup)
    lines = text.split("\n")
    idx = next((i for i, l in enumerate(lines) if re.match(r"^homeassistant:[ \t]*(#.*)?$", l)), None)
    if idx is None:
        text = text.rstrip("\n") + "\n\nhomeassistant:\n" + PKG_LINE
    else:
        nxt = next((l for l in lines[idx + 1:] if l.strip() and not l.lstrip().startswith("#")), "")
        ind = re.match(r"^([ \t]+)", nxt)
        lines.insert(idx + 1, (ind.group(1) if ind else "  ") + "packages: !include_dir_named packages")
        text = "\n".join(lines)
    conf_path.write_text(text, encoding="utf-8")
    (config_dir / "packages").mkdir(exist_ok=True)
    return backup


# ---------------------------------------------------------------- helpers
def _closure(index: dict, ids: list[str]) -> list[str]:
    by_id = {p["id"]: p for p in index["packages"]}
    out: list[str] = []
    seen = set()

    def visit(i: str) -> None:
        if i in seen:
            return
        seen.add(i)
        p = by_id.get(i)
        if not p:
            raise LibraryError(f"Package requis « {i} » absent de la bibliothèque.")
        for r in p.get("requires", []):
            visit(r)
        out.append(i)

    for i in ids:
        visit(i)
    return out


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", yamlutil.slugify(s)) if len(t) > 1}


def _suggest(hass: HomeAssistant, entity_id: str, limit: int = 5) -> list[dict]:
    dom, obj = entity_id.split(".", 1)
    want = _tokens(obj)
    scored = []
    for st in hass.states.async_all(dom):
        have = _tokens(st.object_id) | _tokens(str(st.attributes.get("friendly_name", "")))
        if not want or not have:
            continue
        score = len(want & have) / len(want | have)
        if score > 0:
            scored.append((score, st.entity_id, str(st.attributes.get("friendly_name", ""))))
    scored.sort(reverse=True)
    return [{"entity_id": e, "name": n, "score": round(s, 2)} for s, e, n in scored[:limit]]


def apply_mapping(text: str, mapping: dict[str, str]) -> str:
    keys = [k for k, v in (mapping or {}).items() if v and v != k]
    if not keys:
        return text
    keys.sort(key=len, reverse=True)
    rx = re.compile(r"(?<![\w.])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w])")
    return rx.sub(lambda m: mapping[m.group(1)], text)


def _definitions(body: dict) -> list[dict]:
    """List what a package body defines, with the entity / id used for conflict checks."""
    out = []
    for i, a in enumerate(body.get("automation") or []):
        out.append({"section": "automation", "index": i, "id": str(a.get("id", "")), "label": a.get("alias") or a.get("id")})
    for k in (body.get("script") or {}):
        out.append({"section": "script", "key": k, "entity": f"script.{k}", "label": k})
    for i, s in enumerate(body.get("scene") or []):
        out.append({"section": "scene", "index": i, "id": str(s.get("id", "")), "label": s.get("name")})
    for sec in HELPER_SECTIONS:
        for k in (body.get(sec) or {}):
            out.append({"section": sec, "key": k, "entity": f"{sec}.{k}", "label": f"{sec}.{k}"})
    return out


def _existing_automation_ids(hass: HomeAssistant) -> set[str]:
    comp = hass.data.get("automation")
    ids = set()
    for ent in list(getattr(comp, "entities", []) or []):
        raw = getattr(ent, "raw_config", None) or {}
        if raw.get("id"):
            ids.add(str(raw["id"]))
    return ids


def _read_secret_keys(config_dir: Path) -> set[str]:
    p = config_dir / "secrets.yaml"
    if not p.exists():
        return set()
    try:
        data = yamlutil.load(p.read_text(encoding="utf-8")) or {}
        return set(map(str, data))
    except Exception:  # noqa: BLE001
        return set()


# ---------------------------------------------------------------- plan
async def async_plan(hass: HomeAssistant, root: Path, ids: list[str], mapping: dict, installed: dict) -> dict:
    config_dir = Path(hass.config.config_dir)
    index = await hass.async_add_executor_job(library.read_library, root)
    order = _closure(index, ids)
    pkgs = {}
    for pid in order:
        pkgs[pid] = await hass.async_add_executor_job(library.read_package, root, pid)

    provided = set()
    for p in pkgs.values():
        provided |= set(p.get("provides", []))

    # integrations
    integ_status = {}
    for dom in sorted({i for p in pkgs.values() for i in p.get("integrations", [])}):
        if dom in hass.config.components:
            integ_status[dom] = "chargée"
        else:
            try:
                await async_get_integration(hass, dom)
                integ_status[dom] = "à configurer"
            except IntegrationNotFound:
                integ_status[dom] = "absente"

    # entities
    reg = er.async_get(hass)
    ents = []
    for e in sorted({e for p in pkgs.values() for e in p.get("entities_to_provide", [])} - provided):
        target = mapping.get(e) or e
        exists = hass.states.get(target) is not None or reg.async_get(target) is not None
        ents.append({
            "entity_id": e, "target": mapping.get(e) or "", "exists": exists,
            "suggestions": [] if exists else _suggest(hass, e),
            "packages": [pid for pid, p in pkgs.items() if e in p.get("entities_to_provide", [])],
        })
    notify = []
    for s in sorted({s for p in pkgs.values() for s in p.get("notify_targets", [])}):
        target = mapping.get(s) or s
        dom, svc = target.split(".", 1)
        exists = hass.services.has_service(dom, svc)
        sugg = []
        if not exists:
            sugg = [{"entity_id": f"notify.{n}", "name": n, "score": 0} for n in sorted(hass.services.async_services().get("notify", {})) if n not in ("notify", "send_message", "persistent_notification")][:12]
        notify.append({"entity_id": s, "target": mapping.get(s) or "", "exists": exists, "suggestions": sugg})

    # secrets
    have_secrets = await hass.async_add_executor_job(_read_secret_keys, config_dir)
    secrets = [{"name": s, "exists": s in have_secrets} for s in sorted({s for p in pkgs.values() for s in p.get("secrets", [])})]

    # conflicts
    auto_ids = _existing_automation_ids(hass)
    ours = {d for rec in installed.values() for d in rec.get("definitions", [])}
    conflicts = []
    for pid, p in pkgs.items():
        try:
            body = yamlutil.load(apply_mapping(p["yaml"], mapping)) or {}
        except Exception as err:  # noqa: BLE001
            raise LibraryError(f"package.yaml de « {pid} » invalide : {err}") from err
        for d in _definitions(body):
            key = d.get("entity") or f"automation:{d.get('id')}"
            if key in ours and installed.get(pid):
                continue
            if d.get("entity") and (hass.states.get(d["entity"]) or reg.async_get(d["entity"])):
                conflicts.append({"package": pid, "what": d["label"], "reason": "existe déjà sur cette instance, la définition existante est conservée"})
            elif d["section"] == "automation" and d.get("id") and d["id"] in auto_ids:
                conflicts.append({"package": pid, "what": d["label"], "reason": "une automatisation avec le même identifiant existe déjà, elle est conservée"})

    setup = await hass.async_add_executor_job(packages_setup, config_dir)
    files = []
    for pid, p in pkgs.items():
        for rel in p.get("file_contents", {}):
            files.append({"package": pid, "path": rel, "exists": (config_dir / rel).exists()})

    return {
        "order": order,
        "packages": [{
            "id": pid, "title": p.get("title", pid), "version": p.get("version"),
            "installed_version": (installed.get(pid) or {}).get("version"),
            "explicit": pid in ids, "device_ids": len(p.get("device_ids", [])),
        } for pid, p in pkgs.items()],
        "integrations": integ_status, "entities": ents, "notify": notify, "secrets": secrets,
        "conflicts": conflicts, "files": files, "packages_setup": setup,
        "blocking": [m for m in (
            None if setup["enabled"] or setup["editable"] else setup["reason"],
        ) if m],
        "warnings": [m for m in (
            ("Intégrations absentes de cette instance : " + ", ".join(k for k, v in integ_status.items() if v == "absente")
             + ". Les automatisations qui en dépendent ne fonctionneront qu’une fois installées.") if any(v == "absente" for v in integ_status.values()) else None,
        ) if m],
    }


# ---------------------------------------------------------------- install
async def async_install(hass: HomeAssistant, root: Path, ids: list[str], mapping: dict, secret_values: dict,
                        installed: dict, enable: bool = False, force_update: bool = False) -> dict:
    config_dir = Path(hass.config.config_dir)
    plan = await async_plan(hass, root, ids, mapping, installed)
    missing_secrets = [s["name"] for s in plan["secrets"] if not s["exists"] and not (secret_values or {}).get(s["name"])]
    if missing_secrets:
        raise LibraryError("Valeurs manquantes pour les secrets : " + ", ".join(missing_secrets))
    setup = plan["packages_setup"]
    conf_backup: Path | None = None
    if not setup["enabled"]:
        if not (setup["editable"] and enable):
            raise LibraryError(setup["reason"] + " Cochez « Activer les packages » pour que la bibliothèque l’ajoute.")
        conf_backup = await hass.async_add_executor_job(enable_packages, config_dir)
        setup = await hass.async_add_executor_job(packages_setup, config_dir)

    pkg_dir = config_dir / setup["dir"] / INSTALL_SUBDIR
    reg = er.async_get(hass)
    auto_ids = _existing_automation_ids(hass)
    ours = {d for rec in installed.values() for d in rec.get("definitions", [])}

    todo = []
    for pid in plan["order"]:
        rec = installed.get(pid)
        pinfo = next(p for p in plan["packages"] if p["id"] == pid)
        if rec and rec.get("version") == pinfo["version"] and not force_update:
            continue
        if rec and not pinfo["explicit"] and not force_update:
            continue  # keep the installed dependency as is
        todo.append(pid)

    def write_all() -> dict:
        written: list[tuple[Path, bytes | None]] = []  # (path, previous content)
        records = {}
        reload_domains: set[str] = set()
        restart = False
        pkg_dir.mkdir(parents=True, exist_ok=True)
        for pid in todo:
            p = library.read_package(root, pid)
            body = yamlutil.load(apply_mapping(p["yaml"], mapping)) or {}
            skipped, defs = [], []
            # drop definitions that already exist on this instance (and are not ours)
            for sec in list(body):
                val = body[sec]
                if sec in HELPER_SECTIONS or sec == "script":
                    for k in list(val or {}):
                        ent = f"{sec}.{k}"
                        if ent not in ours and (hass.states.get(ent) or reg.async_get(ent)):
                            skipped.append(ent)
                            del val[k]
                        else:
                            defs.append(ent)
                    if not val:
                        del body[sec]
                elif sec == "automation":
                    keep = []
                    for a in val or []:
                        aid = str(a.get("id", ""))
                        if aid and f"automation:{aid}" not in ours and aid in auto_ids:
                            skipped.append(a.get("alias") or aid)
                        else:
                            keep.append(a)
                            if aid:
                                defs.append(f"automation:{aid}")
                    body[sec] = keep
                    if not keep:
                        del body[sec]
            for sec in body:
                if sec in RELOADABLE:
                    reload_domains.add(sec)
                else:
                    restart = True
            head = "\n".join(line for line in p["yaml"].splitlines()[:6] if line.startswith("#"))
            text = f"{head}\n# Installé par Bibliothèque HA le {_now()} — version {p.get('version')}\n# Ne pas modifier : réinstaller depuis la bibliothèque écrase ce fichier.\n\n" + (yamlutil.dump(body) if body else "{}\n")
            dest = pkg_dir / f"bibliotheque_{pid.replace('-', '_')}.yaml"
            written.append((dest, dest.read_bytes() if dest.exists() else None))
            dest.write_text(text, encoding="utf-8")
            files_written = []
            for rel, content in p.get("file_contents", {}).items():
                fdest = config_dir / rel
                prev_rec = installed.get(pid) or {}
                if fdest.exists() and rel not in prev_rec.get("files", []):
                    skipped.append(rel)
                    continue
                fdest.parent.mkdir(parents=True, exist_ok=True)
                written.append((fdest, fdest.read_bytes() if fdest.exists() else None))
                fdest.write_text(apply_mapping(content, mapping), encoding="utf-8")
                files_written.append(rel)
                if rel.startswith("pyscript/"):
                    reload_domains.add("pyscript")
                elif rel.startswith("python_scripts/"):
                    reload_domains.add("python_script")
                elif rel.startswith("blueprints/"):
                    reload_domains.add("automation")
            records[pid] = {
                "version": p.get("version"), "title": p.get("title", pid), "file": dest.relative_to(config_dir).as_posix(),
                "files": files_written, "definitions": defs, "skipped": skipped, "installed_at": _now(),
                "requires": p.get("requires", []), "mapping": {k: v for k, v in mapping.items() if v and k in (p["yaml"] + "".join(p.get("file_contents", {}).values()))},
                "sections": sorted(body),
            }
        # secrets
        sec_path = config_dir / "secrets.yaml"
        new_secrets = {k: v for k, v in (secret_values or {}).items() if v}
        if new_secrets:
            have = _read_secret_keys(config_dir)
            add = {k: v for k, v in new_secrets.items() if k not in have}
            if add:
                written.append((sec_path, sec_path.read_bytes() if sec_path.exists() else None))
                with sec_path.open("a", encoding="utf-8") as fh:
                    fh.write("\n# Ajouté par Bibliothèque HA\n" + yamlutil.dump(add))
        return {"written": written, "records": records, "reload": reload_domains, "restart": restart}

    def rollback(written: list[tuple[Path, bytes | None]]) -> None:
        for path, prev in reversed(written):
            if prev is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(prev)
        if conf_backup:
            shutil.copy2(conf_backup, config_dir / "configuration.yaml")

    if not todo:
        return {"installed": [], "skipped_up_to_date": plan["order"], "restart_required": False, "records": {}}

    before = await _async_check(hass)
    res = await hass.async_add_executor_job(write_all)
    after = await _async_check(hass)
    new_problems = [m for m in after if m not in before]
    if new_problems:
        await hass.async_add_executor_job(rollback, res["written"])
        raise LibraryError("La vérification de la configuration a échoué, rien n’a été installé :\n" + "\n".join(new_problems))

    restart = res["restart"]
    reloaded = await _async_reload(hass, res["reload"])
    return {
        "installed": list(res["records"]), "records": res["records"], "reloaded": reloaded,
        "restart_required": restart, "packages_enabled_now": conf_backup is not None,
        "skipped_up_to_date": [p for p in plan["order"] if p not in todo],
    }


async def _async_check(hass: HomeAssistant) -> list[str]:
    """Errors and component warnings of a full configuration check."""
    from homeassistant.helpers import check_config

    res = await check_config.async_check_ha_config_file(hass)
    return [str(e.message) for e in list(res.errors) + list(res.warnings)]


async def _async_reload(hass: HomeAssistant, domains: set[str]) -> list[str]:
    done = []
    order = sorted(domains, key=lambda d: (d in ("automation", "script", "scene"), d))  # helpers/templates first
    for dom in order:
        if hass.services.has_service(dom, "reload"):
            try:
                await hass.services.async_call(dom, "reload", blocking=True)
                done.append(dom)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Rechargement de %s impossible : %s", dom, err)
    return done


async def async_uninstall(hass: HomeAssistant, pid: str, installed: dict, force: bool = False) -> dict:
    rec = installed.get(pid)
    if not rec:
        raise LibraryError(f"« {pid} » n’est pas installé.")
    users = [o for o, r in installed.items() if o != pid and pid in r.get("requires", [])]
    if users and not force:
        raise LibraryError("Ces packages installés en ont besoin : " + ", ".join(users))
    config_dir = Path(hass.config.config_dir)

    def remove() -> None:
        (config_dir / rec["file"]).unlink(missing_ok=True)
        for rel in rec.get("files", []):
            (config_dir / rel).unlink(missing_ok=True)

    await hass.async_add_executor_job(remove)
    domains = set(rec.get("sections", [])) & RELOADABLE
    if any(f.startswith("pyscript/") for f in rec.get("files", [])):
        domains.add("pyscript")
    reloaded = await _async_reload(hass, domains)
    await hass.async_block_till_done()
    # remove registry entries left behind (they would show as "unavailable" forever)
    reg = er.async_get(hass)
    cleaned = []
    for d in rec.get("definitions", []):
        if d.startswith("automation:"):
            eid = reg.async_get_entity_id("automation", "automation", d.split(":", 1)[1])
        else:
            eid = d if reg.async_get(d) else None
        if not eid:
            continue
        st = hass.states.get(eid)
        if st is None or st.attributes.get("restored"):
            reg.async_remove(eid)
            cleaned.append(eid)
    return {"removed": pid, "reloaded": reloaded, "registry_cleaned": cleaned,
            "restart_required": bool(set(rec.get("sections", [])) - RELOADABLE)}
