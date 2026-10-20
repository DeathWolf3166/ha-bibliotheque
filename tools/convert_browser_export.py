"""Convert the browser export (ha-export-*.json) into a scanner snapshot, then analyze it.

Usage: python3 tools/convert_browser_export.py ha-export.json [rules.yaml] > analysis.json
Useful offline; the integration's own scanner reads much more (YAML templates, files…).
"""
import json, sys, importlib.util, pathlib, types
base = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ha_library"
pkg = types.ModuleType("ha_library"); pkg.__path__ = [str(base)]; sys.modules["ha_library"] = pkg
def load(name):
    spec = importlib.util.spec_from_file_location(f"ha_library.{name}", base / f"{name}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m); return m
yamlutil = load("yamlutil"); analyzer = load("analyzer")

def convert(L):
    items = []
    for a in L["automations"]:
        c = a["config"]; key = str(c.get("id") or a["entity_id"].split(".", 1)[1])
        items.append({"uid": f"automation:{key}", "kind": "automation", "domain": "automation", "key": key,
                      "name": c.get("alias") or key, "description": c.get("description") or "", "config": c,
                      "provides": [a["entity_id"]], "emit": {"section": "automation", "mode": "list"},
                      "enabled": a.get("state") != "off"})
    for s in L["scripts"]:
        key = s["entity_id"].split(".", 1)[1]; c = s["config"]
        items.append({"uid": f"script:{key}", "kind": "script", "domain": "script", "key": key,
                      "name": c.get("alias") or key, "description": c.get("description") or "", "config": c,
                      "provides": [s["entity_id"]], "emit": {"section": "script", "mode": "dict", "key": key}})
    for z in L["scenes"]:
        c = z["config"] or {"name": z["name"], "entities": {e: "on" for e in z["attributes"].get("entity_id", [])}}
        key = str(c.get("id") or z["entity_id"].split(".", 1)[1])
        items.append({"uid": f"scene:{key}", "kind": "scene", "domain": "scene", "key": key, "name": z["name"],
                      "description": "", "config": c, "provides": [z["entity_id"]], "emit": {"section": "scene", "mode": "list"}})
    for h in L["helpers"]:
        dom, key = h["entity_id"].split(".", 1); a = h["attributes"]
        cfg = {"name": a.get("friendly_name", key)}
        if a.get("icon"): cfg["icon"] = a["icon"]
        for k in {"input_number": ("min", "max", "step", "mode", "unit_of_measurement"), "input_select": ("options",),
                  "input_text": ("min", "max", "mode"), "input_datetime": ("has_date", "has_time"), "timer": ("duration", "restore")}.get(dom, ()):
            if k in a: cfg[k] = a[k]
        items.append({"uid": f"helper:{h['entity_id']}", "kind": "helper", "domain": dom, "key": key, "name": cfg["name"],
                      "description": "", "config": cfg, "provides": [h["entity_id"]], "emit": {"section": dom, "mode": "dict", "key": key}})
    ents = {e: {"platform": p} for e, p in L["registry"].items()}
    return {"format": 1, "instance": {"name": "Maison", "slug": "maison", "ha_version": "?", "exported_at": L["meta"]["exported"], "entity_count": L["meta"]["entity_count"]},
            "items": items, "entities": ents, "integrations": L["integrations"], "views": [], "resources": [], "orphans": L["orphans"]}

if __name__ == "__main__":
    L = json.load(open(sys.argv[1]))
    rules = yamlutil.load(open(sys.argv[2]).read()) if len(sys.argv) > 2 else {}
    snap = convert(L)
    res = analyzer.analyze(snap, rules, {})
    json.dump(yamlutil.to_jsonable(res), sys.stdout, ensure_ascii=False)
