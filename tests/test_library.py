"""End-to-end: scan a source instance, export, then install on a fresh instance."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from homeassistant import config as conf_util
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_library import yamlutil
from custom_components.ha_library.const import DOMAIN

SOURCE_CONF = """
homeassistant:
  name: Source
  packages: !include_dir_named packages
automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
input_boolean:
  mode_nuit:
    name: Mode nuit
    icon: mdi:weather-night
input_number:
  delai_lumiere:
    name: Délai lumière
    min: 1
    max: 30
    step: 1
template:
  - sensor:
      - name: Lumières allumées
        unique_id: lumieres_allumees
        state: "{{ states.light | selectattr('state','eq','on') | list | count }}"
shell_command:
  notifier_webhook: "curl -X POST https://example.com/hook/SUPERSECRET123456"
"""
SECRETS = "hook_url: SUPERSECRET123456\napi_cle: sk-abcdefghijklmnop1234\n"
AUTOMATIONS = """
- id: '1001'
  alias: Éclairage • Couloir la nuit
  triggers:
    - trigger: state
      entity_id: binary_sensor.mouvement_couloir
      to: "on"
  conditions:
    - condition: state
      entity_id: input_boolean.mode_nuit
      state: "on"
  actions:
    - action: light.turn_on
      target: {entity_id: light.couloir}
      data: {brightness_pct: 20}
    - delay: "{{ states('input_number.delai_lumiere') | int }}"
    - action: script.eteindre_couloir
- id: '1002'
  alias: Éclairage • Compteur
  triggers:
    - trigger: state
      entity_id: sensor.lumieres_allumees
  actions:
    - action: shell_command.notifier_webhook
- id: '1003'
  alias: Alerte fuite
  triggers:
    - trigger: webhook
      webhook_id: abcdef0123456789abcdef
  actions:
    - action: notify.mobile_app_iphone_de_test
      data: {message: Fuite}
"""
AUTOMATIONS += """
- id: '1788125445557'
  alias: SMS gardien
  triggers: [{trigger: time, at: "21:04:00"}]
  actions:
    - action: notify.sms
      data: {message: Coucou, target: "+33 6 12 34 56 78"}
"""
SCRIPTS = """
eteindre_couloir:
  alias: Éteindre couloir
  sequence:
    - action: light.turn_off
      target: {entity_id: light.couloir}
"""
SCENES = """
- id: '2001'
  name: Soirée
  entities:
    light.couloir: {state: "on", brightness: 120}
"""
PKG = """
input_boolean:
  vacances:
    name: Vacances
"""


def _write(base: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


async def _load_yaml_domains(hass: HomeAssistant) -> None:
    conf = await conf_util.async_hass_config_yaml(hass)
    for dom in ("input_boolean", "input_number", "template", "shell_command", "script", "automation", "scene"):
        assert await async_setup_component(hass, dom, conf), dom
    await hass.async_block_till_done()


async def _setup_library(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={"instance_name": "Source"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def lib_out(tmp_path_factory):
    return tmp_path_factory.mktemp("lib")


async def test_scan_and_export(hass: HomeAssistant, hass_ws_client, tmp_path, lib_out) -> None:
    hass.config.config_dir = str(tmp_path)
    _write(tmp_path, {
        "configuration.yaml": SOURCE_CONF, "secrets.yaml": SECRETS, "automations.yaml": AUTOMATIONS,
        "scripts.yaml": SCRIPTS, "scenes.yaml": SCENES, "packages/vacances.yaml": PKG,
        "pyscript/outils.py": "@service\ndef saluer(nom=None):\n    log.info(f'bonjour {nom}')\n    light.turn_on(entity_id='light.couloir')\n",
    })
    await _load_yaml_domains(hass)
    hass.states.async_set("light.couloir", "off")
    hass.states.async_set("binary_sensor.mouvement_couloir", "off")
    await _setup_library(hass)

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/scan"})
    res = await ws.receive_json()
    assert res["success"], res
    r = res["result"]
    pk = {p["id"]: p for p in r["packages"]}
    print(json.dumps({k: (v["title"], v["items"], v["requires"], v["entities_to_provide"]) for k, v in pk.items()}, ensure_ascii=False, indent=1))
    ecl = pk["eclairage"]
    # the automations, their script and helpers end up in one package
    assert "automation:1001" in ecl["items"] and "script:eteindre_couloir" in ecl["items"]
    assert "helper:input_boolean.mode_nuit" in ecl["items"]
    assert "template:sensor.lumieres_allumees" in ecl["items"]
    assert "yaml:shell_command:notifier_webhook" in ecl["items"]
    assert ecl["entities_to_provide"] == ["binary_sensor.mouvement_couloir", "light.couloir"]
    # each definition is owned by one package only
    owners = [u for p in r["packages"] for u in p["items"]]
    assert len(owners) == len(set(owners))
    # secrets are written back as !secret
    assert "!secret hook_url_texte" in ecl["yaml"]
    alerte = next(p for p in r["packages"] if "automation:1003" in p["items"])
    assert "!secret" in alerte["yaml"] and "abcdef0123456789abcdef" not in alerte["yaml"]
    assert "notify.mobile_app_iphone_de_test" in alerte["notify_targets"]
    assert any(i["kind"] == "file" for i in r["items"].values())
    sms = next(p for p in r["packages"] if "automation:1788125445557" in p["items"])
    assert "id: '1788125445557'" in sms["yaml"] and "21:04:00" in sms["yaml"]
    assert "+33 6 12 34 56 78" not in sms["yaml"] and "!secret" in sms["yaml"]
    # the YAML package parses and contains every section
    body = yamlutil.load(ecl["yaml"])
    assert set(body) >= {"automation", "script", "template", "input_boolean", "input_number", "shell_command"}

    # rename + contexts override survives a new analysis
    await ws.send_json({"id": 2, "type": "ha_library/override", "package_id": "eclairage", "title": "Éclairage nocturne", "contexts": ["particulier", "hotel"]})
    res = await ws.receive_json()
    assert res["success"], res
    assert next(p for p in res["result"]["packages"] if p["id"] == "eclairage")["contexts"] == ["particulier", "hotel"]

    await ws.send_json({"id": 3, "type": "ha_library/export", "package_ids": [p["id"] for p in r["packages"]]})
    res = await ws.receive_json()
    assert res["success"], res
    root = tmp_path / "ha_library" / "library"
    assert (root / "library.json").exists()
    assert (root / "packages" / "eclairage" / "package.yaml").exists()
    idx = json.loads((root / "library.json").read_text())
    assert any(p["title"] == "Éclairage nocturne" for p in idx["packages"])
    shutil.copytree(root, lib_out / "library", dirs_exist_ok=True)

    await ws.send_json({"id": 4, "type": "ha_library/library", "source_id": "local"})
    res = await ws.receive_json()
    assert res["success"] and res["result"]["packages"]



async def test_install(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    """Install a package built by analyzer on an instance without packages enabled."""
    from custom_components.ha_library import analyzer, library

    snap = {
        "instance": {"name": "Source", "slug": "source", "ha_version": "x", "exported_at": "2026-10-20T00:00:00", "entity_count": 3},
        "items": [
            {"uid": "automation:1001", "kind": "automation", "domain": "automation", "key": "1001", "name": "Éclairage • Couloir",
             "config": {"id": "1001", "alias": "Éclairage • Couloir", "triggers": [{"trigger": "state", "entity_id": "binary_sensor.mouvement_couloir", "to": "on"}],
                        "conditions": [{"condition": "state", "entity_id": "input_boolean.mode_nuit", "state": "on"}],
                        "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.couloir"}}, {"action": "script.eteindre_couloir"},
                                    {"action": "shell_command.ping", "data": {}}]},
             "provides": ["automation.eclairage_couloir"], "emit": {"section": "automation", "mode": "list"}},
            {"uid": "automation:1002", "kind": "automation", "domain": "automation", "key": "1002", "name": "Éclairage • Secret",
             "config": {"id": "1002", "alias": "Éclairage • Secret", "triggers": [{"trigger": "webhook", "webhook_id": yamlutil.SecretRef("mon_webhook"), "local_only": True}], "actions": []},
             "provides": ["automation.eclairage_secret"], "emit": {"section": "automation", "mode": "list"}},
            {"uid": "script:eteindre_couloir", "kind": "script", "domain": "script", "key": "eteindre_couloir", "name": "Éteindre couloir",
             "config": {"alias": "Éteindre couloir", "sequence": [{"action": "light.turn_off", "target": {"entity_id": "light.couloir"}}]},
             "provides": ["script.eteindre_couloir"], "emit": {"section": "script", "mode": "dict", "key": "eteindre_couloir"}},
            {"uid": "helper:input_boolean.mode_nuit", "kind": "helper", "domain": "input_boolean", "key": "mode_nuit", "name": "Mode nuit",
             "config": {"name": "Mode nuit"}, "provides": ["input_boolean.mode_nuit"], "emit": {"section": "input_boolean", "mode": "dict", "key": "mode_nuit"}},
            {"uid": "yaml:shell_command:ping", "kind": "yaml", "domain": "shell_command", "key": "ping", "name": "ping",
             "config": "echo ok", "provides": ["shell_command.ping"], "emit": {"section": "shell_command", "mode": "dict", "key": "ping"}},
        ],
        "entities": {"light.couloir": {"platform": "hue"}, "binary_sensor.mouvement_couloir": {"platform": "zha"}},
        "views": [], "resources": [],
    }
    analysis = analyzer.analyze(snap)
    assert [p["id"] for p in analysis["packages"]] == ["eclairage"]
    hass.config.config_dir = str(tmp_path)
    root = tmp_path / "ha_library" / "library"
    library.write_export(root, analysis, snap, ["eclairage"])

    _write(tmp_path, {"configuration.yaml": "homeassistant:\n  name: Cible\n\nlogger:\n  default: info\n"})
    for dom in ("automation", "script", "input_boolean", "shell_command"):
        assert await async_setup_component(hass, dom, {})
    hass.states.async_set("light.lumiere_couloir", "off", {"friendly_name": "Lumière couloir"})
    hass.states.async_set("binary_sensor.pir_couloir", "off", {"friendly_name": "Mouvement couloir"})
    await _setup_library(hass)
    ws = await hass_ws_client(hass)

    await ws.send_json({"id": 1, "type": "ha_library/plan", "source_id": "local", "package_ids": ["eclairage"]})
    res = await ws.receive_json()
    assert res["success"], res
    plan = res["result"]
    assert plan["packages_setup"]["editable"] and not plan["packages_setup"]["enabled"]
    ents = {e["entity_id"]: e for e in plan["entities"]}
    assert ents["light.couloir"]["suggestions"][0]["entity_id"] == "light.lumiere_couloir"
    assert plan["secrets"] == [{"name": "mon_webhook", "exists": False}]

    # refused without the secret
    await ws.send_json({"id": 2, "type": "ha_library/install", "source_id": "local", "package_ids": ["eclairage"], "enable_packages": True})
    res = await ws.receive_json()
    assert not res["success"] and "mon_webhook" in res["error"]["message"]

    mapping = {"light.couloir": "light.lumiere_couloir", "binary_sensor.mouvement_couloir": "binary_sensor.pir_couloir"}
    await ws.send_json({"id": 3, "type": "ha_library/install", "source_id": "local", "package_ids": ["eclairage"],
                        "enable_packages": True, "mapping": mapping, "secrets": {"mon_webhook": "abc123"}})
    res = await ws.receive_json()
    assert res["success"], res
    out = res["result"]
    assert out["installed"] == ["eclairage"] and out["packages_enabled_now"]
    conf_text = (tmp_path / "configuration.yaml").read_text()
    assert "packages: !include_dir_named packages" in conf_text
    written = (tmp_path / "packages" / "bibliotheque" / "bibliotheque_eclairage.yaml").read_text()
    assert "light.lumiere_couloir" in written and "light.couloir" not in written
    assert "!secret mon_webhook" in written
    assert "mon_webhook: abc123" in (tmp_path / "secrets.yaml").read_text()
    await hass.async_block_till_done()
    # reloaded: the automation, script and helper exist
    assert hass.states.get("input_boolean.mode_nuit") is not None
    assert hass.states.get("script.eteindre_couloir") is not None
    assert any(s.attributes.get("id") == "1001" for s in hass.states.async_all("automation"))

    # installing again: up to date
    await ws.send_json({"id": 4, "type": "ha_library/install", "source_id": "local", "package_ids": ["eclairage"]})
    res = await ws.receive_json()
    assert res["success"] and res["result"]["skipped_up_to_date"] == ["eclairage"]

    # uninstall
    await ws.send_json({"id": 5, "type": "ha_library/uninstall", "package_id": "eclairage"})
    res = await ws.receive_json()
    assert res["success"], res
    await hass.async_block_till_done()
    assert not (tmp_path / "packages" / "bibliotheque" / "bibliotheque_eclairage.yaml").exists()
    assert hass.states.get("script.eteindre_couloir") is None


async def test_install_rollback_on_bad_config(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    from custom_components.ha_library import library

    hass.config.config_dir = str(tmp_path)
    _write(tmp_path, {"configuration.yaml": "homeassistant:\n  packages: !include_dir_named packages\n"})
    root = tmp_path / "ha_library" / "library" / "packages" / "casse"
    _write(root, {"package.yaml": "input_number:\n  sans_bornes:\n    name: Sans bornes\n", "manifest.json": json.dumps({"id": "casse", "title": "Cassé", "version": "1"})})
    assert await async_setup_component(hass, "input_number", {})
    await _setup_library(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/install", "source_id": "local", "package_ids": ["casse"]})
    res = await ws.receive_json()
    assert not res["success"]
    assert "vérification" in res["error"]["message"]
    assert not (tmp_path / "packages" / "bibliotheque" / "bibliotheque_casse.yaml").exists()


MESSY_CONF = """
homeassistant:
  name: Messy
automation: !include automations.yaml
sensor:
  - platform: template
    sensors:
      temperature_moyenne:
        friendly_name: Température moyenne
        value_template: "{{ (states('sensor.t1')|float(0) + states('sensor.t2')|float(0)) / 2 }}"
template:
  - trigger:
      - trigger: time_pattern
        hours: "/1"
    sensor:
      - name: Compteur horaire
        state: "{{ now().hour }}"
utility_meter:
  conso_jour:
    source: sensor.energie_totale
    cycle: daily
    tariffs: [hc, hp]
counter:
  passages:
    name: Passages
"""
MESSY_AUTOS = """
- id: bp1
  alias: Lumière auto (blueprint)
  use_blueprint:
    path: homeassistant/motion_light.yaml
    input:
      motion_entity: binary_sensor.pir
      light_target: {entity_id: light.cuisine}
- id: tarif
  alias: Bascule tarif
  triggers: [{trigger: time, at: "22:00:00"}]
  actions:
    - action: select.select_option
      target: {entity_id: select.conso_jour}
      data: {option: hc}
    - action: counter.increment
      target: {entity_id: counter.passages}
    - action: input_boolean.turn_on
      target: {entity_id: input_boolean.cree_dans_ui}
"""


async def test_scan_messy_config(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    hass.config.config_dir = str(tmp_path)
    import homeassistant.components.automation as auto_mod
    src_bp = Path(auto_mod.__file__).parent / "blueprints" / "motion_light.yaml"
    _write(tmp_path, {
        "configuration.yaml": MESSY_CONF, "automations.yaml": MESSY_AUTOS,
        "blueprints/automation/homeassistant/motion_light.yaml": src_bp.read_text(),
        ".storage/input_boolean": json.dumps({"version": 1, "minor_version": 1, "key": "input_boolean", "data": {"items": [{"id": "cree_dans_ui", "name": "Créé dans l’UI", "icon": "mdi:check"}]}}),
        ".storage/lovelace": json.dumps({"version": 1, "key": "lovelace", "data": {"config": {"views": [{"title": "Accueil", "path": "home", "cards": [{"type": "custom:button-card", "entity": "light.cuisine"}]}]}}}),
    })
    conf = await conf_util.async_hass_config_yaml(hass)
    for dom in ("input_boolean", "counter", "template", "sensor", "utility_meter", "automation"):
        assert await async_setup_component(hass, dom, conf), dom
    await hass.async_block_till_done()
    await _setup_library(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/scan"})
    res = await ws.receive_json()
    assert res["success"], res
    r = res["result"]
    uids = set(r["items"])
    assert "yaml:sensor.temperature_moyenne" in uids
    assert any(u.startswith("template:") and "compteur" in u for u in uids)
    assert "yaml:utility_meter:conso_jour" in uids
    assert "helper:input_boolean.cree_dans_ui" in uids and "helper:counter.passages" in uids
    assert "file:blueprints/automation/homeassistant/motion_light.yaml" in uids
    tarif = next(p for p in r["packages"] if "automation:tarif" in p["items"])
    # utility meter, counter and UI helper follow the automation that uses them
    assert {"yaml:utility_meter:conso_jour", "helper:counter.passages", "helper:input_boolean.cree_dans_ui"} <= set(tarif["items"])
    bp_pkg = next(p for p in r["packages"] if "automation:bp1" in p["items"])
    assert "file:blueprints/automation/homeassistant/motion_light.yaml" in bp_pkg["items"]
    assert r["views"] and r["views"][0]["custom_cards"] == ["button-card"]
    body = yamlutil.load(tarif["yaml"])
    assert body["utility_meter"]["conso_jour"]["tariffs"] == ["hc", "hp"]
