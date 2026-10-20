"""Automation → blueprint conversion, saved and then used by a real automation."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ha_library import blueprint as bpmod
from custom_components.ha_library.const import DOMAIN

AUTO = {
    "id": "1001", "alias": "Couloir la nuit", "description": "Allume le couloir la nuit",
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.mouvement_couloir", "to": "on"}],
    "conditions": [{"condition": "template", "value_template": "{{ is_state('input_boolean.mode_nuit', 'on') and states.sensor.lux.state | int(0) < 50 }}"}],
    "actions": [
        {"action": "light.turn_on", "target": {"entity_id": "light.couloir"}, "data": {"brightness_pct": 20}},
        {"action": "notify.mobile_app_iphone", "data": {"message": "Mouvement"}},
    ],
    "mode": "single",
}


def test_conversion() -> None:
    res = bpmod.to_blueprint(AUTO)
    y = res["yaml"]
    assert "!input binary_sensor_mouvement_couloir" in y and "!input light_couloir" in y
    assert "is_state(v_input_boolean_mode_nuit," in y and "states[v_sensor_lux].state" in y
    assert "!input notify_mobile_app_iphone" in y
    assert res["unconverted"] == []
    assert "id: '1001'" not in y


async def test_blueprint_used_by_automation(hass: HomeAssistant, hass_ws_client, tmp_path) -> None:
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n")
    entry = MockConfigEntry(domain=DOMAIN, data={"instance_name": "T"}); entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id); await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    res = bpmod.to_blueprint(AUTO)
    await ws.send_json({"id": 1, "type": "ha_library/blueprint/save", "yaml": res["yaml"], "domain": "automation", "filename": "couloir.yaml"})
    out = await ws.receive_json()
    assert out["success"], out
    assert out["result"]["path"] == "blueprints/automation/bibliotheque/couloir.yaml"

    lights = async_mock_service(hass, "light", "turn_on")
    notes = async_mock_service(hass, "notify", "mobile_app_pixel")
    hass.states.async_set("input_boolean.nuit", "on")
    hass.states.async_set("sensor.luminosite", "10")
    hass.states.async_set("binary_sensor.pir", "off")
    assert await async_setup_component(hass, "automation", {"automation": [{
        "alias": "Depuis blueprint",
        "use_blueprint": {"path": "bibliotheque/couloir.yaml", "input": {
            "binary_sensor_mouvement_couloir": "binary_sensor.pir", "input_boolean_mode_nuit": "input_boolean.nuit",
            "sensor_lux": "sensor.luminosite", "light_couloir": "light.entree", "notify_mobile_app_iphone": "notify.mobile_app_pixel"}},
    }]})
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.pir", "on")
    await hass.async_block_till_done()
    assert len(lights) == 1 and lights[0].data["entity_id"] == ["light.entree"]
    assert len(notes) == 1

    # saving twice is refused without overwrite
    await ws.send_json({"id": 2, "type": "ha_library/blueprint/save", "yaml": res["yaml"], "domain": "automation", "filename": "couloir.yaml"})
    assert not (await ws.receive_json())["success"]
