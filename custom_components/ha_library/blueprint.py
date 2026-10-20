"""Turn a library automation (or script) into a Home Assistant blueprint.

Every entity, device and notification service the item references becomes a
blueprint input. Plain fields get `!input name`; inside templates the entity is
read from a variable (`states('sensor.x')` → `states(v_sensor_x)`).
"""
from __future__ import annotations

import copy
import re
from typing import Any

from . import yamlutil
from .analyzer import ENT_RX, references
from .yamlutil import TaggedValue, slugify

TEMPLATE_RX = re.compile(r"\{\{|\{%")


def _input_name(entity_id: str) -> str:
    return slugify(entity_id.replace(".", "_"))[:60]


def to_blueprint(config: dict, domain: str = "automation", name: str | None = None,
                 description: str = "", devices: dict | None = None, source: str = "") -> dict:
    cfg = copy.deepcopy(config)
    for k in ("id", "alias"):
        cfg.pop(k, None)
    refs = references(cfg)
    ents = sorted(e for e in refs["entities"] if e != "sun.sun")
    notify = sorted(s for s in refs["services"] if s.startswith("notify.") and s.split(".")[1] not in ("notify", "send_message"))
    devs = sorted(refs["devices"])
    devices = devices or {}

    inputs: dict[str, dict] = {}
    by_entity: dict[str, str] = {}
    for e in ents:
        n = _input_name(e)
        dom = e.split(".")[0]
        by_entity[e] = n
        inputs[n] = {"name": e, "description": f"Entité ({dom}) — à l’origine : {e}", "selector": {"entity": {"filter": [{"domain": dom}]}}}
    by_device: dict[str, str] = {}
    for i, d in enumerate(devs, 1):
        info = devices.get(d) or {}
        n = f"appareil_{i}"
        by_device[d] = n
        sel: dict = {}
        if info.get("integrations"):
            sel["filter"] = [{"integration": info["integrations"][0]}]
        label = info.get("name") or d
        inputs[n] = {"name": f"Appareil : {label}", "description": " · ".join(x for x in (info.get("manufacturer"), info.get("model")) if x) or "Appareil",
                     "selector": {"device": sel}}
    by_notify: dict[str, str] = {}
    for s in notify:
        n = _input_name(s)
        by_notify[s] = n
        inputs[n] = {"name": f"Notification ({s})", "description": "Service de notification à utiliser, ex. notify.mobile_app_mon_telephone",
                     "default": s, "selector": {"text": {}}}

    unconverted: set[str] = set()

    def in_template(text: str) -> str:
        def q(m: re.Match) -> str:
            eid = m.group(2)
            return f"v_{by_entity[eid]}" if eid in by_entity else m.group(0)

        text = re.sub(r"(['\"])([a-z_]+\.[a-z0-9_]+)\1", q, text)

        def attr(m: re.Match) -> str:
            eid = f"{m.group(1)}.{m.group(2)}"
            return f"states[v_{by_entity[eid]}]" if eid in by_entity else m.group(0)

        text = re.sub(r"states\.([a-z_]+)\.([a-z0-9_]+)", attr, text)
        for m in ENT_RX.finditer(text):
            if m.group(0) in by_entity:
                unconverted.add(m.group(0))
        return text

    used_vars: set[str] = set()

    def walk(o: Any, key: str | None = None) -> Any:
        if isinstance(o, dict):
            return {k: walk(v, str(k)) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v, key) for v in o]
        if isinstance(o, str):
            if o in by_entity and not TEMPLATE_RX.search(o):
                return TaggedValue("!input", by_entity[o])
            if key == "device_id" and o in by_device:
                return TaggedValue("!input", by_device[o])
            if key in ("action", "service") and o in by_notify:
                return TaggedValue("!input", by_notify[o])
            if TEMPLATE_RX.search(o):
                new = in_template(o)
                for e, n in by_entity.items():
                    if f"v_{n}" in new and f"v_{n}" not in o:
                        used_vars.add(n)
                return new
            if ENT_RX.search(o):
                for m in ENT_RX.finditer(o):
                    if m.group(0) in by_entity:
                        unconverted.add(m.group(0))
        return o

    body = walk(cfg)
    if used_vars:
        variables = {f"v_{n}": TaggedValue("!input", n) for n in sorted(used_vars)}
        if isinstance(body.get("variables"), dict):
            variables.update(body["variables"])
        body = {"variables": variables, **{k: v for k, v in body.items() if k != "variables"}}

    bp = {
        "blueprint": {
            "name": name or config.get("alias") or "Blueprint Bibliothèque HA",
            "description": (description or config.get("description") or "").strip() or "Créé par Bibliothèque HA.",
            "domain": domain,
            "author": "Bibliothèque HA",
            "input": inputs,
        },
        **body,
    }
    if source:
        bp["blueprint"]["source_url"] = source
    return {"blueprint": bp, "yaml": yamlutil.dump(bp), "inputs": len(inputs), "unconverted": sorted(unconverted)}
