"""View installation into a storage dashboard and ghost entry cleanup."""
from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_library.const import DOMAIN


async def _setup(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n")
    assert await async_setup_component(hass, "lovelace", {})
    entry = MockConfigEntry(domain=DOMAIN, data={"instance_name": "Test"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_install_view(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    await _setup(hass, tmp_path)
    lib = tmp_path / "ha_library" / "library" / "views"
    lib.mkdir(parents=True)
    (lib / "maison-salon.yaml").write_text("title: Salon\npath: salon\ncards:\n- type: custom:button-card\n  entity: light.salon\n- type: entities\n  entities: [sensor.temp]\n")
    hass.states.async_set("light.lumiere_salon", "on")
    ws = await hass_ws_client(hass)
    # default dashboard in storage mode, with an existing "salon" view
    await ws.send_json({"id": 1, "type": "lovelace/config/save", "config": {"views": [{"title": "Accueil", "path": "salon", "cards": []}]}})
    assert (await ws.receive_json())["success"]

    await ws.send_json({"id": 2, "type": "ha_library/dashboards"})
    res = await ws.receive_json()
    assert res["success"] and res["result"][0]["url_path"] == "lovelace" and res["result"][0]["mode"] == "storage"

    await ws.send_json({"id": 3, "type": "ha_library/view/install", "source_id": "local", "view_id": "maison-salon",
                        "dashboard": "lovelace", "mapping": {"light.salon": "light.lumiere_salon"}})
    res = await ws.receive_json()
    assert res["success"], res
    r = res["result"]
    assert r["path"] == "salon-2"
    assert r["missing_cards"] == ["button-card"]
    assert r["missing_entities"] == ["sensor.temp"]
    assert (tmp_path / r["backup"]).exists()

    await ws.send_json({"id": 4, "type": "lovelace/config"})
    cfg = (await ws.receive_json())["result"]
    assert [v["path"] for v in cfg["views"]] == ["salon", "salon-2"]
    assert cfg["views"][1]["cards"][0]["entity"] == "light.lumiere_salon"


async def test_ghosts(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    await _setup(hass, tmp_path)
    reg = er.async_get(hass)
    reg.async_get_or_create("automation", "automation", "old1", suggested_object_id="ancienne")
    reg.async_get_or_create("automation", "automation", "live1", suggested_object_id="vivante")
    hass.states.async_set("automation.vivante", "on")
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/ghosts"})
    res = await ws.receive_json()
    assert [g["entity_id"] for g in res["result"]] == ["automation.ancienne"]
    # a live entity is never removed, even if asked
    await ws.send_json({"id": 2, "type": "ha_library/ghosts/remove", "entity_ids": ["automation.ancienne", "automation.vivante"]})
    res = await ws.receive_json()
    assert res["result"]["removed"] == ["automation.ancienne"]
    assert reg.async_get("automation.ancienne") is None and reg.async_get("automation.vivante") is not None
