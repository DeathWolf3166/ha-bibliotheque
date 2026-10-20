"""Dependency analysis and grouping of a scanned instance into library packages.

Pure Python (no Home Assistant import) so it can run in tests and offline tools.

A *snapshot* (built by scanner.py) is a list of items. Each item provides
entities/services and references others. Root items (automations, scripts,
scenes) are grouped by: user override → rule → HA category → alias prefix →
"divers". Support items (helpers, templates, YAML platforms, files) follow the
package that uses them most, so every definition lives in exactly one package
(two packages defining the same helper would break HA's package merge).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any

from . import yamlutil
from .yamlutil import SecretRef, slugify

ENTITY_DOMAINS = (
    "alarm_control_panel|automation|binary_sensor|button|calendar|camera|climate|counter|cover|"
    "device_tracker|event|fan|group|humidifier|image|input_boolean|input_button|input_datetime|"
    "input_number|input_select|input_text|lawn_mower|light|lock|media_player|number|person|"
    "remote|scene|schedule|script|select|sensor|siren|switch|text|timer|todo|update|vacuum|valve|"
    "water_heater|weather|zone|sun|conversation|ai_task|tts|stt|wake_word|assist_satellite|notify"
)
ENT_RX = re.compile(r"(?<![\w.])(" + ENTITY_DOMAINS + r")\.([a-z0-9_]*[a-z0-9])(?![\w({])")
SERVICE_RX = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
SERVICE_KEYS = {"action", "service"}
HELPER_DOMAINS = {
    "input_boolean", "input_number", "input_select", "input_text", "input_datetime",
    "input_button", "timer", "counter", "schedule",
}
# service verbs that look like object ids when written as "light.turn_on" in a template
SERVICE_VERBS = {
    "turn_on", "turn_off", "toggle", "set_value", "set_datetime", "select_option", "start",
    "cancel", "reload", "press", "increment", "decrement", "reset", "set_options", "select_next",
    "select_previous", "pause", "finish", "change", "trigger", "send_command", "play_media",
}
# entities that exist on every instance
UNIVERSAL = {"sun.sun", "zone.home"}
# integrations every instance has, never listed as a requirement
CORE_INTEGRATIONS = {
    "homeassistant", "persistent_notification", "logbook", "system_log", "automation", "script",
    "scene", "template", "input_boolean", "input_number", "input_select", "input_text",
    "input_datetime", "input_button", "timer", "counter", "schedule", "sun", "zone", "person",
    "group", "notify", "tts", "conversation", "frontend", "logger", "recorder", "history",
    "light", "switch", "sensor", "binary_sensor", "media_player", "climate", "cover", "fan",
    "vacuum", "camera", "lock", "select", "number", "button", "event", "calendar", "todo",
    "weather", "update", "device_tracker", "siren", "text", "valve", "remote", "image",
    "humidifier", "water_heater", "lawn_mower", "alarm_control_panel", "assist_satellite",
    "ai_task", "shell_command", "rest_command", "utility_meter", "python_script",
}
PREFIX_SPLIT = re.compile(r"\s+(?:-|–|—|•|·|\||:|→)\s+|\s*:\s+")
CONTEXTS = ["particulier", "hotel", "logistique", "bureau"]
ROOT_KINDS = {"automation", "script", "scene"}


# ---------------------------------------------------------------- references
def references(config: Any) -> dict[str, set[str]]:
    """Entities, services, device ids and blueprint paths used by a config."""
    ents: set[str] = set()
    services: set[str] = set()
    devices: set[str] = set()
    blueprints: set[str] = set()

    PAYLOAD_KEYS = {"data", "event_data", "variables", "data_template", "payload"}

    def walk(o: Any, key: str | None = None, payload: bool = False) -> None:
        if isinstance(o, SecretRef):
            return
        if isinstance(o, yamlutil.TaggedValue):
            walk(o.value, key, payload)
            return
        if isinstance(o, dict):
            if "use_blueprint" in o and isinstance(o["use_blueprint"], dict):
                path = o["use_blueprint"].get("path")
                if path:
                    blueprints.add(str(path))
            for k, v in o.items():
                walk(v, str(k), payload or str(k) in PAYLOAD_KEYS)
            return
        if isinstance(o, list):
            for v in o:
                walk(v, key, payload)
            return
        if not isinstance(o, str):
            return
        # "action:" inside a notification payload (Android intents, actionable buttons) is not a service call
        if key in SERVICE_KEYS and not payload and SERVICE_RX.match(o):
            services.add(o)
            return
        if key == "device_id":
            devices.add(o)
            return
        for m in ENT_RX.finditer(o):
            if m.group(2) in SERVICE_VERBS:
                continue
            ents.add(m.group(0))

    walk(config)
    # "script.my_script" called as a service is also an entity dependency
    for s in services:
        dom, obj = s.split(".", 1)
        if dom == "script" and obj not in SERVICE_VERBS:
            ents.add(s)
    return {"entities": ents, "services": services, "devices": devices, "blueprints": blueprints}


# ---------------------------------------------------------------- grouping
def _match_rule(rules: list[dict], text: str) -> dict | None:
    for r in rules:
        rx = r.get("match")
        if rx and re.search(rx, text, re.I):
            return r
    return None


def _prefix(name: str, strip: list[str]) -> str | None:
    n = name.strip()
    # drop decorative leading emoji/punctuation
    n = re.sub(r"^[^\w]+", "", n)
    for s in strip:
        n = re.sub(rf"^{re.escape(s)}\s*(?:-|–|—|•|·|:)\s*", "", n, flags=re.I)
    parts = PREFIX_SPLIT.split(n, maxsplit=1)
    if len(parts) == 2 and 2 <= len(parts[0]) <= 40:
        return parts[0].strip()
    # "Chauffage lit • Btn3" style already handled; try first two words for "Interrupteur - X"
    return None


def analyze(snapshot: dict, rules: dict | None = None, overrides: dict | None = None) -> dict:
    rules = rules or {}
    overrides = overrides or {}
    rule_groups: list[dict] = list(rules.get("groups") or [])
    strip_prefixes: list[str] = list(rules.get("strip_prefixes") or [])
    pkg_over: dict = overrides.get("packages") or {}
    item_over: dict = overrides.get("items") or {}

    items: dict[str, dict] = {i["uid"]: dict(i) for i in snapshot["items"]}
    known = set(snapshot.get("entities") or {})
    ent_info: dict = snapshot.get("entities") or {}

    # provider index
    provider: dict[str, str] = {}
    for uid, it in items.items():
        for p in it.get("provides") or []:
            provider.setdefault(p, uid)
        it["_refs"] = references(it.get("config"))
    # second pass (providers complete)
    for uid, it in items.items():
        refs = it["_refs"]
        deps = set()
        for e in refs["entities"] | refs["services"]:
            p = provider.get(e)
            if p and p != uid:
                deps.add(p)
        for bp in refs["blueprints"]:
            p = provider.get("blueprint:" + bp)
            if p:
                deps.add(p)
        it["_deps"] = deps
    users: dict[str, set[str]] = defaultdict(set)
    for uid, it in items.items():
        for d in it["_deps"]:
            users[d].add(uid)

    # ---- assign roots
    group_meta: dict[str, dict] = {}
    assign: dict[str, str] = {}

    def ensure_group(gid: str, title: str, description: str = "", contexts: list[str] | None = None) -> str:
        if gid not in group_meta:
            group_meta[gid] = {"title": title, "description": description, "contexts": contexts or ["particulier"]}
        return gid

    for r in rule_groups:
        ensure_group(r["id"], r.get("title", r["id"]), r.get("description", ""), r.get("contexts"))

    def text_of(it: dict) -> str:
        objs = " ".join(slugify(p.split(".", 1)[-1]) for p in it.get("provides") or [] if "." in p)
        return slugify(it.get("key", "")) + " " + objs + " " + slugify(it.get("name", ""))

    def try_explicit(uid: str, it: dict) -> bool:
        if uid in item_over:
            gid = item_over[uid]
            ensure_group(gid, gid)
            assign[uid] = gid
            return True
        r = _match_rule(rule_groups, text_of(it))
        if r:
            assign[uid] = r["id"]
            return True
        if it.get("category"):
            gid = slugify(it["category"]).replace("_", "-")
            ensure_group(gid, it["category"])
            assign[uid] = gid
            return True
        return False

    roots = [u for u, it in items.items() if it["kind"] in ROOT_KINDS]
    pending = []
    for uid in roots:
        if not try_explicit(uid, items[uid]):
            pending.append(uid)

    # prefixes shared by at least two roots
    pref_of = {u: _prefix(items[u].get("name") or "", strip_prefixes) for u in pending}
    counts = Counter(slugify(p) for p in pref_of.values() if p)
    later = []
    for uid in pending:
        it = items[uid]
        p = pref_of[uid]
        if p and counts[slugify(p)] >= 2:
            gid = slugify(p).replace("_", "-")
            ensure_group(gid, p)
            assign[uid] = gid
        else:
            later.append(uid)

    # affinity: an ungrouped script/scene used by a single package joins it
    for _ in range(3):
        rest = []
        for uid in later:
            pk = {assign[u] for u in users.get(uid, ()) if u in assign}
            if len(pk) == 1:
                assign[uid] = pk.pop()
            else:
                rest.append(uid)
        later = rest
    # an ungrouped automation that calls scripts of a single package joins it
    rest = []
    for uid in later:
        pk = {assign[d] for d in items[uid]["_deps"] if d in assign and items[d]["kind"] in ROOT_KINDS}
        if len(pk) == 1:
            assign[uid] = pk.pop()
        else:
            rest.append(uid)
    # first significant word shared by ≥2 remaining roots ("Dreame …", "Lavage …")
    STOP = {"le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "a", "au", "the", "auto", "automatique", "nouvelle", "test"}

    def first_word(it: dict) -> str | None:
        n = re.sub(r"^[^\w]+", "", it.get("name") or "")
        for s in strip_prefixes:
            n = re.sub(rf"^{re.escape(s)}\s*(?:-|–|—|•|·|:)?\s*", "", n, flags=re.I)
        for w in re.split(r"[^\w]+", n):
            if len(w) > 2 and slugify(w) not in STOP and not w.isdigit():
                return w
        return None

    fw = {u: first_word(items[u]) for u in rest}
    wc = Counter(slugify(w) for w in fw.values() if w)
    rest2 = []
    for uid in rest:
        w = fw[uid]
        if w and wc[slugify(w)] >= 2:
            gid = slugify(w).replace("_", "-")
            ensure_group(gid, w[:1].upper() + w[1:])
            assign[uid] = gid
        else:
            rest2.append(uid)
    # roots sharing helpers/templates/scripts form a family
    parent = {u: u for u in rest2}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_dep: dict[str, list[str]] = defaultdict(list)
    for uid in rest2:
        for dep in items[uid]["_deps"]:
            by_dep[dep].append(uid)
        by_dep[uid].append(uid)
    for members in by_dep.values():
        for m in members[1:]:
            parent[find(m)] = find(members[0])
    comps: dict[str, list[str]] = defaultdict(list)
    for uid in rest2:
        comps[find(uid)].append(uid)
    for members in comps.values():
        if len(members) >= 2:
            lead = sorted(members, key=lambda u: items[u].get("name") or "")[0]
            title = items[lead].get("name") or lead
            gid = "famille-" + slugify(title)[:40].replace("_", "-")
            ensure_group(gid, f"{title} (et liés)", "Éléments qui partagent des helpers ou des scripts.")
            for m in members:
                assign[m] = gid
        else:
            assign[members[0]] = ensure_group("divers", "Divers", "Éléments sans famille commune.")

    # ---- support items follow their users (iterate for chains)
    support = [u for u in items if u not in assign]
    for _ in range(6):
        changed = False
        for uid in support:
            if uid in assign:
                continue
            if uid in item_over:
                assign[uid] = ensure_group(item_over[uid], item_over[uid])
                changed = True
                continue
            c = Counter(assign[u] for u in users.get(uid, ()) if u in assign)
            if c:
                best = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                assign[uid] = best
                changed = True
        if not changed:
            break
    # unused support items: rule → prefix → bucket per kind
    for uid in support:
        if uid in assign:
            continue
        it = items[uid]
        r = _match_rule(rule_groups, text_of(it))
        if r:
            assign[uid] = r["id"]
            continue
        bucket = {"helper": "helpers-non-utilises", "template": "templates", "yaml": "yaml-divers", "file": "fichiers"}.get(it["kind"], "divers")
        titles = {
            "helpers-non-utilises": ("Helpers non utilisés", "Helpers qu’aucune automatisation ni aucun script ne référence."),
            "templates": ("Capteurs template", "Capteurs calculés non rattachés à une automatisation."),
            "yaml-divers": ("Configuration YAML", "Plateformes et domaines YAML non rattachés à une automatisation."),
            "fichiers": ("Scripts Python et blueprints", "pyscript, python_scripts et blueprints non rattachés."),
            "divers": ("Divers", "Éléments sans famille commune."),
        }[bucket]
        assign[uid] = ensure_group(bucket, *titles)

    # ---- build packages
    by_pkg: dict[str, list[str]] = defaultdict(list)
    for uid, gid in assign.items():
        by_pkg[gid].append(uid)

    packages: dict[str, dict] = {}
    for gid, uids in by_pkg.items():
        meta = dict(group_meta[gid])
        meta.update({k: v for k, v in (pkg_over.get(gid) or {}).items() if k in ("title", "description", "contexts", "exclude")})
        uids.sort(key=lambda u: (["automation", "script", "scene", "helper", "template", "yaml", "file"].index(items[u]["kind"]) if items[u]["kind"] in ROOT_KINDS | {"helper", "template", "yaml", "file"} else 9, items[u].get("name") or ""))
        provides = set()
        for u in uids:
            provides |= set(items[u].get("provides") or [])
        packages[gid] = {"id": gid, **meta, "items": uids, "provides": sorted(provides)}

    for gid, p in packages.items():
        req = set()
        ents: set[str] = set()
        services: set[str] = set()
        devices: set[str] = set()
        for u in p["items"]:
            it = items[u]
            for d in it["_deps"]:
                if assign[d] != gid:
                    req.add(assign[d])
            ents |= it["_refs"]["entities"]
            services |= it["_refs"]["services"]
            devices |= it["_refs"]["devices"]
        p["requires"] = sorted(req)
        p["_ents"], p["_services"], p["device_ids"] = ents, services, sorted(devices)

    def closure(gid: str) -> set[str]:
        seen, stack = set(), [gid]
        while stack:
            g = stack.pop()
            if g in seen:
                continue
            seen.add(g)
            stack.extend(packages[g]["requires"])
        return seen

    for gid, p in packages.items():
        provided = set()
        for g in closure(gid):
            provided |= set(packages[g]["provides"])
        p["entities_to_provide"] = sorted(e for e in p["_ents"] if e not in provided and e not in UNIVERSAL)
        p["notify_targets"] = sorted({s for s in p["_services"] if s.startswith("notify.") and s not in provided and s.split(".")[1] not in ("notify", "send_message", "persistent_notification")})
        p["missing_on_source"] = sorted(e for e in p["entities_to_provide"] if e not in known)
        integ = set()
        for s in p["_services"]:
            dom = s.split(".")[0]
            if dom not in CORE_INTEGRATIONS:
                integ.add(dom)
            if dom == "notify":
                target = s.split(".", 1)[1]
                if target.startswith("mobile_app_"):
                    integ.add("mobile_app")
                elif target.startswith("alexa_media"):
                    integ.add("alexa_media")
        for e in p["entities_to_provide"]:
            info = ent_info.get(e) or {}
            plat = info.get("platform")
            if plat and plat not in CORE_INTEGRATIONS:
                integ.add(plat)
        for u in p["items"]:
            integ |= set(items[u].get("integrations") or [])
        p["integrations"] = sorted(integ - CORE_INTEGRATIONS)
        secrets = set()
        for u in p["items"]:
            secrets |= yamlutil.secrets_in(items[u].get("config"))
        p["secrets"] = sorted(secrets)
        kinds = Counter(items[u]["kind"] for u in p["items"])
        p["counts"] = {k: kinds.get(k, 0) for k in ("automation", "script", "scene", "helper", "template", "yaml", "file")}
        p["files"] = [items[u]["file"]["path"] for u in p["items"] if items[u].get("file")]
        for k in ("_ents", "_services"):
            p.pop(k)
        p["yaml"] = build_package_yaml(p, [items[u] for u in p["items"]])
        p["version"] = hashlib.sha1((p["yaml"] + "".join(items[u]["file"]["content"] for u in p["items"] if items[u].get("file"))).encode()).hexdigest()[:10]

    item_view = {}
    for uid, it in items.items():
        refs = it["_refs"]
        item_view[uid] = {
            k: it.get(k) for k in ("uid", "kind", "domain", "key", "name", "description", "category", "enabled", "provides", "file")
        } | {
            "package": assign[uid],
            "uses": sorted(it["_deps"]),
            "used_by": sorted(users.get(uid, ())),
            "entities": sorted(refs["entities"]),
            "services": sorted(refs["services"]),
            "missing": sorted(e for e in refs["entities"] if e not in known and e not in provider and e not in UNIVERSAL),
            "yaml": "" if it.get("file") else yamlutil.dump(it.get("config")),
        }
    return {"packages": sorted(packages.values(), key=lambda p: p["title"].lower()), "items": item_view}


# ---------------------------------------------------------------- package yaml
def build_package_body(items: list[dict]) -> dict:
    body: dict[str, Any] = {}
    for it in items:
        emit = it.get("emit")
        if not emit:
            continue
        sec, mode = emit["section"], emit["mode"]
        if mode == "list":
            lst = body.setdefault(sec, [])
            if it["config"] not in lst:
                lst.append(it["config"])
        else:
            body.setdefault(sec, {})[emit["key"]] = it["config"]
    # stable section order
    order = ["automation", "script", "scene", "template"]
    out = {k: body[k] for k in order if k in body}
    for k in sorted(body):
        if k not in out:
            out[k] = body[k]
    return out


def build_package_yaml(pkg: dict, items: list[dict]) -> str:
    head = [
        f"# Bibliothèque HA — {pkg['title']}",
        f"# {pkg.get('description') or ''}".rstrip(),
        f"# Contextes : {', '.join(pkg.get('contexts') or [])}",
        f"# Intégrations requises : {', '.join(pkg.get('integrations') or []) or 'aucune'}",
        f"# Packages requis : {', '.join(pkg.get('requires') or []) or 'aucun'}",
        "",
    ]
    body = build_package_body(items)
    return "\n".join(head) + "\n" + (yamlutil.dump(body) if body else "{}\n")
