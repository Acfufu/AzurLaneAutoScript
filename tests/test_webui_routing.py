"""Webui routing behavior tests: navigations fall back to the SPA home,
API/asset requests get honest JSON 404s.

The frontend is a hash router (#/xxx in the URL fragment), which the
browser never sends to the server, so the server only owns the registered
API routes, "/" and the static assets. Browser navigations (Accept:
text/html) to anything else must 302 back to "/" (loop-guarded when the
SPA build is missing); fetch/asset loads must get a JSON 404 instead of
being redirected into index.html (audit L3).
"""

import os

import httpx
import pytest

from module.webui.api import create_api_app

DIST_BUILT = os.path.isfile(os.path.join("webapp", "dist", "index.html"))

# What a browser navigation sends; fetch()/EventSource/asset loads don't.
BROWSER_ACCEPT = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


@pytest.fixture
async def client():
    # httpx ASGI transport instead of starlette.testclient.TestClient:
    # starlette deprecates its TestClient in favor of httpx2, and httpx is
    # already a dev dependency. ASGITransport does not run the lifespan,
    # matching the previous no-lifespan TestClient usage.
    transport = httpx.ASGITransport(app=create_api_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.anyio
async def test_unknown_path_redirects_home(client):
    response = await client.get("/nonexistent-xyz-123", headers=BROWSER_ACCEPT, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


@pytest.mark.anyio
async def test_unknown_path_without_html_accept_gets_json_404(client):
    # fetch()/EventSource/asset loads don't ask for text/html, so they must
    # not be redirected into index.html — that used to surface as a MIME
    # white screen or a "Bad response" SyntaxError (audit L3).
    response = await client.get("/nonexistent-xyz-123", follow_redirects=False)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.anyio
async def test_deep_path_redirects_home(client):
    response = await client.get("/deep/link/page", headers=BROWSER_ACCEPT, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


@pytest.mark.anyio
async def test_missing_asset_gets_json_404(client):
    # A stale shell referencing a deleted asset must see a clean 404, not
    # HTML served under a .js name (audit L3).
    response = await client.get("/assets/index-does-not-exist.js", follow_redirects=False)
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


@pytest.mark.anyio
async def test_api_typo_redirects_home_for_navigations(client):
    # Typing an API path in the address bar is still a navigation (Accept:
    # text/html) and keeps the SPA fallback.
    response = await client.get("/api/status", headers=BROWSER_ACCEPT, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


@pytest.mark.anyio
async def test_registered_route_still_works(client):
    # /i18n/{lang} needs no lifespan state and always answers 200.
    response = await client.get("/i18n/zh-CN")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_root_never_redirect_loops(client):
    # When dist is built, "/" serves the SPA; when it is not, "/" must
    # return the JSON 404 rather than redirect to itself.
    response = await client.get("/", follow_redirects=False)
    if DIST_BUILT:
        assert response.status_code == 200
    else:
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


@pytest.mark.anyio
async def test_hash_fragment_is_client_side(client):
    # The browser never sends the #fragment; the server only sees "/"
    # and the SPA router handles the hash. Pin that the server treats the
    # path without the fragment as the SPA root.
    response = await client.get("/", follow_redirects=False)
    if DIST_BUILT:
        assert response.status_code == 200
    else:
        assert response.status_code == 404


@pytest.mark.anyio
async def test_run_rejects_unknown_instance(client):
    # /run used to spawn a manager for any name (phantom instance, then a
    # default-config main loop); reject it before any state is created.
    response = await client.post("/run", json={"instance": "no-such-instance"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "not found" in body["error"]


@pytest.mark.anyio
async def test_run_rejects_unknown_func(client):
    # An unmatched func used to return ok:true while the child process
    # logged "No function matched" and exited — the silent no-op behind
    # the tool-page start incident. Validation happens before any manager
    # is touched, so no lifespan state is needed here.
    response = await client.post("/run", json={"instance": "alas", "func": "audit_nonexistent_probe"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "No function matched: audit_nonexistent_probe"


@pytest.mark.anyio
async def test_instance_new_rejects_invalid_chars(client):
    # "x/y" used to return ok:true and write config/x/y.json — an instance
    # /status never lists (audit M3). Same character validation as rename.
    response = await client.post("/instance/new", json={"name": "x/y"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Invalid characters" in body["error"]
    assert not os.path.exists(os.path.join("config", "x"))


@pytest.mark.anyio
async def test_stop_rejects_unknown_instance(client):
    # /stop used to lazily create a persistent manager entry for any name
    # it was handed (audit L6). Unknown names must be rejected before any
    # bookkeeping exists.
    from module.webui.process_manager import ProcessManager

    response = await client.post("/stop", json={"instance": "no-such-instance"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "no-such-instance" not in ProcessManager._processes


@pytest.mark.anyio
async def test_config_unknown_instance_rejected(client):
    # GET used to answer 200 with a full default config and POST used to
    # write the file into existence — a ghost instance /status never lists
    # (audit M10). All three shapes must 404 before touching the disk.
    get = await client.get("/config/no-such-instance")
    assert get.status_code == 404
    post = await client.post("/config/no-such-instance", json={"value": {"Alas.Optimization.ScreenshotInterval": 0.5}})
    assert post.status_code == 404
    export = await client.get("/config/no-such-instance/export")
    assert export.status_code == 404
    assert not os.path.exists(os.path.join("config", "no-such-instance.json"))


@pytest.mark.anyio
async def test_config_template_write_rejected(client):
    # Importing over template.json must not be possible (audit M6/M10):
    # template stays readable but is never writable.
    post = await client.post("/config/template/import", json={"config": {"Alas": {}}})
    assert post.status_code == 403


def test_list_mod_instance_ignores_unknown_mod_suffix(tmp_path, monkeypatch):
    # Any dotted file used to qualify as a mod instance (audit L5):
    # alas.backup.json became instance "alas" with mod "backup" and crashed
    # the main loop on the unknown mod. Known mods (maa) still enumerate.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "alas.backup.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "alas.maa.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from module.submodule.utils import get_config_mod, list_mod_instance

    assert list_mod_instance() == ["alas"]
    assert get_config_mod("alas") == "maa"


def test_alas_instance_dedupes_base_and_mod_bridge(tmp_path, monkeypatch):
    # alas.json and alas.maa.json both map to instance "alas"; the list
    # used to contain the same name twice.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "alas.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "alas.maa.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from module.config.utils import alas_instance

    instances = alas_instance()
    assert instances.count("alas") == 1


@pytest.mark.anyio
async def test_config_import_creates_and_clears_serial(tmp_path, monkeypatch):
    # Import is the sanctioned way to restore a backup: it may create a new
    # instance, must refuse template targets and invalid names (M6/M10),
    # and must not carry the source machine's emulator serial over.
    import json as jsonlib

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "template.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    transport = httpx.ASGITransport(app=create_api_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        payload = {"Alas": {"Emulator": {"Serial": "127.0.0.1:5555", "PackageName": "com.YoStarEN.AzurLane"}}}
        res = await test_client.post("/config/audit-imp/import", json={"config": payload})
        assert res.status_code == 200
        assert res.json()["ok"] is True
        saved = jsonlib.loads((tmp_path / "config" / "audit-imp.json").read_text(encoding="utf-8"))
        assert saved["Alas"]["Emulator"]["Serial"] == ""
        assert saved["Alas"]["Emulator"]["PackageName"] == "com.YoStarEN.AzurLane"

        res = await test_client.post("/config/template/import", json={"config": {}})
        assert res.status_code == 403
        res = await test_client.post("/config/template-backup/import", json={"config": {}})
        assert res.status_code == 403
        # A slash can't even reach the handler (Starlette keeps %2F out of
        # the path param → static-mount 405, nothing written); other invalid
        # characters do arrive and must be rejected by name validation.
        res = await test_client.post("/config/a%2Fb/import", json={"config": {}})
        assert res.status_code != 200
        res = await test_client.post("/config/a:b/import", json={"config": {}})
        assert res.status_code == 404
        assert not (tmp_path / "config" / "a").exists()
        assert not (tmp_path / "config" / "a:b.json").exists()


@pytest.mark.anyio
async def test_mod_instance_config_is_readonly(tmp_path, monkeypatch):
    # The webui used to read/write config/alas.json for instance "alas"
    # while the maa bridge lives in config/alas.maa.json — editing was a
    # silent no-op (audit M9). Reads now serve the real file; writes are
    # refused; /configs reports the /status name.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "alas.maa.json").write_text('{"Maa": {"say": 1}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    transport = httpx.ASGITransport(app=create_api_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        res = await test_client.get("/configs")
        assert [c["name"] for c in res.json()] == ["alas"]

        res = await test_client.get("/config/alas")
        assert res.status_code == 200
        assert res.json() == {"Maa": {"say": 1}}

        res = await test_client.post("/config/alas", json={"value": {"Maa.say": 2}})
        assert res.status_code == 403
        res = await test_client.post("/config/alas/import", json={"config": {}})
        assert res.status_code == 403

        res = await test_client.get("/config/alas/export")
        assert res.status_code == 200
        assert b'"say": 1' in res.content

        # the plain file must never have been created by any of the above
        assert not (tmp_path / "config" / "alas.json").exists()


def test_schema_instance_server(tmp_path, monkeypatch):
    # Select options resolve against the edited instance's game server,
    # not a hardcoded cn (audit M8).
    import json as jsonlib

    (tmp_path / "config").mkdir()
    cfg = tmp_path / "config" / "alas.json"
    cfg.write_text(jsonlib.dumps({"Alas": {"Emulator": {"PackageName": "com.YoStarEN.AzurLane"}}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from module.webui.api.routers.schema import _instance_server

    assert _instance_server("alas") == "en"
    cfg.write_text("{}", encoding="utf-8")
    assert _instance_server("alas") == "cn"
