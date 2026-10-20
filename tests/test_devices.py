"""device_id references: described at export, matched by model at install."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_library import analyzer, library
from custom_components.ha_library.const import DOMAIN

OLD = "0123456789abcdef0123456789abcdef"


async def test_device_mapping(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n  packages: !include_dir_named packages\n")
    snap = {
        "instance": {"name": "Source", "slug": "source", "ha_version": "x", "exported_at": "2026-10-20T00:00:00", "entity_count": 1},
        "items": [{
            "uid": "automation:b1", "kind": "automation", "domain": "automation", "key": "b1", "name": "Bouton • Salon",
            "config": {"id": "b1", "alias": "Bouton • Salon",
                       "triggers": [{"trigger": "device", "domain": "zha", "device_id": OLD, "type": "remote_button_short_press", "subtype": "turn_on"}],
                       "actions": [{"action": "light.toggle", "target": {"entity_id": "light.salon"}}]},
            "provides": ["automation.bouton_salon"], "emit": {"section": "automation", "mode": "list"},
        }],
        "entities": {}, "devices": {OLD: {"name": "Bouton salon", "manufacturer": "IKEA", "model": "TRADFRI on/off switch", "integrations": ["zha"]}},
    }
    an = analyzer.analyze(snap)
    pkg = an["packages"][0]
    assert pkg["devices"][0]["model"] == "TRADFRI on/off switch"
    library.write_export(tmp_path / "ha_library" / "library", an, snap, [pkg["id"]])

    for dom in ("automation", "light"):
        assert await async_setup_component(hass, dom, {})
    zha = MockConfigEntry(domain="zha"); zha.add_to_hass(hass)
    other = MockConfigEntry(domain="hue"); other.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    new = dev_reg.async_get_or_create(config_entry_id=zha.entry_id, identifiers={("zha", "x1")}, manufacturer="IKEA", model="TRADFRI on/off switch", name="Interrupteur chambre")
    dev_reg.async_get_or_create(config_entry_id=other.entry_id, identifiers={("hue", "y")}, manufacturer="Signify", model="Hue bulb", name="Ampoule")

    entry = MockConfigEntry(domain=DOMAIN, data={"instance_name": "Cible"}); entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id); await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/plan", "source_id": "local", "package_ids": [pkg["id"]]})
    res = await ws.receive_json()
    assert res["success"], res
    devs = res["result"]["devices"]
    assert devs[0]["exists"] is False
    assert devs[0]["suggestions"][0]["id"] == new.id
    assert all(s["model"] != "Hue bulb" for s in devs[0]["suggestions"])

    await ws.send_json({"id": 2, "type": "ha_library/install", "source_id": "local", "package_ids": [pkg["id"]], "mapping": {OLD: new.id}})
    res = await ws.receive_json()
    assert res["success"], res
    text = (tmp_path / "packages" / "bibliotheque" / f"bibliotheque_{pkg['id'].replace('-', '_')}.yaml").read_text()
    assert new.id in text and OLD not in text
