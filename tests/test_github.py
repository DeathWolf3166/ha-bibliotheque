"""GitHub source download and publication (HTTP mocked)."""
from __future__ import annotations

import io
import json
import zipfile

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_library.const import DOMAIN


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("maxime-lib-abc123/library.json", json.dumps({"format": 1, "packages": [{"id": "p1", "title": "Package 1", "version": "v1"}], "views": [], "resources": [], "instances": []}))
        z.writestr("maxime-lib-abc123/packages/p1/package.yaml", "input_boolean:\n  test_p1:\n    name: Test\n")
        z.writestr("maxime-lib-abc123/packages/p1/manifest.json", json.dumps({"id": "p1", "title": "Package 1", "version": "v1"}))
        z.writestr("maxime-lib-abc123/../evil.txt", "x")
    return buf.getvalue()


async def _setup(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("homeassistant:\n")
    entry = MockConfigEntry(domain=DOMAIN, data={"instance_name": "Test"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_github_fetch_and_publish(hass: HomeAssistant, hass_ws_client, aioclient_mock, tmp_path) -> None:
    await _setup(hass, tmp_path)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/settings/set", "source": {"repo": "https://github.com/maxime/lib", "branch": "main", "token": "ghp_x"}, "publish_to": "gh:maxime/lib"})
    res = await ws.receive_json()
    assert res["success"], res
    src = next(s for s in res["result"]["sources"] if s["id"] == "gh:maxime/lib")
    assert src["has_token"] and "token" not in src

    aioclient_mock.get("https://api.github.com/repos/maxime/lib/zipball/main", content=_zip())
    await ws.send_json({"id": 2, "type": "ha_library/source/refresh", "source_id": "gh:maxime/lib"})
    res = await ws.receive_json()
    assert res["success"], res
    assert res["result"]["files"] == 3
    assert not (tmp_path / "ha_library" / "evil.txt").exists()
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer ghp_x"

    await ws.send_json({"id": 3, "type": "ha_library/library", "source_id": "gh:maxime/lib"})
    res = await ws.receive_json()
    assert res["success"] and res["result"]["packages"][0]["id"] == "p1"

    # publish the local library (one commit through the git data API)
    local = tmp_path / "ha_library" / "library" / "packages" / "p2"
    local.mkdir(parents=True)
    (local / "package.yaml").write_text("{}\n")
    base = "https://api.github.com/repos/maxime/lib"
    aioclient_mock.get(f"{base}/git/ref/heads/main", json={"object": {"sha": "head1"}})
    aioclient_mock.get(f"{base}/git/commits/head1", json={"tree": {"sha": "tree1"}})
    aioclient_mock.post(f"{base}/git/trees", json={"sha": "tree2"}, status=201)
    aioclient_mock.post(f"{base}/git/commits", json={"sha": "commit2"}, status=201)
    aioclient_mock.patch(f"{base}/git/refs/heads/main", json={}, status=200)
    await ws.send_json({"id": 4, "type": "ha_library/publish", "source_id": "gh:maxime/lib"})
    res = await ws.receive_json()
    assert res["success"], res
    assert res["result"]["commit"] == "commit2"
    tree_call = next(c for c in aioclient_mock.mock_calls if c[0] == "POST" and str(c[1]).endswith("/git/trees"))
    assert tree_call[2]["base_tree"] == "tree1"
    assert any(e["path"] == "packages/p2/package.yaml" for e in tree_call[2]["tree"])


async def test_private_repo_without_token(hass: HomeAssistant, hass_ws_client, aioclient_mock, tmp_path) -> None:
    await _setup(hass, tmp_path)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ha_library/settings/set", "source": {"repo": "maxime/prive"}})
    assert (await ws.receive_json())["success"]
    aioclient_mock.get("https://api.github.com/repos/maxime/prive/zipball/main", status=404)
    await ws.send_json({"id": 2, "type": "ha_library/source/refresh", "source_id": "gh:maxime/prive"})
    res = await ws.receive_json()
    assert not res["success"] and "jeton" in res["error"]["message"]


async def test_panel_registered(hass: HomeAssistant, hass_client, tmp_path) -> None:
    await _setup(hass, tmp_path)
    assert "bibliotheque" in hass.data["frontend_panels"]
    client = await hass_client()
    resp = await client.get("/ha_library_static/ha-library-panel.js")
    assert resp.status == 200
    assert "customElements.define" in await resp.text()
