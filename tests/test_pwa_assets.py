"""The PWA's static wiring.

Pure Python, no browser and no node, so it runs in the ordinary unit suite. It
catches the failure mode that static assets actually have: a reference to a file
that is not there. A missing icon or a precache entry pointing at a deleted
script does not raise anywhere — the app just quietly stops installing, or the
service worker refuses to activate.
"""

import json
import re
from pathlib import Path

import pytest
from httpx import AsyncClient

WEB = Path(__file__).resolve().parent.parent / "web"

pytestmark = pytest.mark.skipif(not (WEB / "index.html").exists(), reason="no web/ directory")


def read(*parts: str) -> str:
    return (WEB.joinpath(*parts)).read_text(encoding="utf-8")


# --- referenced assets --------------------------------------------------------


def test_every_asset_referenced_by_the_shell_exists() -> None:
    for ref in re.findall(r'(?:href|src)="(/[^"]+)"', read("index.html")):
        assert (WEB / ref.lstrip("/")).exists(), ref


def test_the_shell_pulls_nothing_from_a_cdn() -> None:
    """An offline-first app cannot depend on a network it may not have."""
    html = read("index.html")
    assert "https://" not in html
    assert "cdn." not in html


def test_alpine_is_vendored() -> None:
    vendored = list((WEB / "vendor").glob("alpine-*.min.js"))
    assert vendored, "Alpine must be vendored, not loaded from a CDN"
    assert vendored[0].stat().st_size > 10_000


# --- manifest -----------------------------------------------------------------


def test_manifest_is_valid_and_installable() -> None:
    manifest = json.loads(read("manifest.json"))
    for key in ("name", "short_name", "start_url", "display", "icons"):
        assert key in manifest, key
    assert manifest["display"] == "standalone"
    assert manifest["start_url"].startswith(manifest.get("scope", "/"))


def test_manifest_icons_exist_and_include_a_maskable_one() -> None:
    """Without a maskable icon, Android crops the launcher icon badly."""
    icons = json.loads(read("manifest.json"))["icons"]
    for icon in icons:
        assert (WEB / icon["src"].lstrip("/")).exists(), icon["src"]
    assert any(icon.get("purpose") == "maskable" for icon in icons)
    assert any(icon.get("sizes") == "512x512" for icon in icons)


def test_png_icons_are_real_pngs_of_the_declared_size() -> None:
    """A manifest can promise 512x512 and ship something else entirely."""
    import struct

    for icon in json.loads(read("manifest.json"))["icons"]:
        if not icon["src"].endswith(".png"):
            continue
        data = (WEB / icon["src"].lstrip("/")).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", icon["src"]
        width, height = struct.unpack(">II", data[16:24])
        declared = int(icon["sizes"].split("x")[0])
        assert (width, height) == (declared, declared), icon["src"]


# --- service worker -----------------------------------------------------------


def test_every_precached_file_exists() -> None:
    """A precache entry that 404s makes `install` reject and the SW never activates."""
    shell = re.search(r"const SHELL = \[(.*?)\];", read("sw.js"), re.S)
    assert shell
    for path in re.findall(r"'([^']+)'", shell.group(1)):
        target = "index.html" if path == "/" else path.lstrip("/")
        assert (WEB / target).exists(), path


def test_service_worker_handles_push_and_clicks() -> None:
    sw = read("sw.js")
    assert "addEventListener('push'" in sw
    assert "addEventListener('notificationclick'" in sw
    assert "showNotification" in sw


def test_api_requests_are_network_first() -> None:
    """A cached streak or proof ETA is worse than a spinner — they age in minutes."""
    sw = read("sw.js")
    assert "networkFirst" in sw
    assert "/api/" in sw


def test_writes_are_never_intercepted_by_the_cache() -> None:
    """Mutations belong to the outbox; a service worker replaying them would double-post."""
    assert "request.method !== 'GET'" in read("sw.js")


# --- Alpine bindings ----------------------------------------------------------


def component_members() -> set[str]:
    source = read("js", "app.js")
    return set(re.findall(r"^\s{4}(?:async )?(\w+)\(", source, re.M)) | set(
        re.findall(r"^\s{4}(\w+):", source, re.M)
    )


def test_every_event_handler_is_defined_on_the_component() -> None:
    """Alpine fails silently at runtime when a handler does not exist."""
    html = read("index.html")
    called = set(re.findall(r'@click="(\w+)\(', html)) | set(
        re.findall(r'@submit\.prevent="(\w+)\(', html)
    )
    assert called, "expected some handlers"
    assert called <= component_members(), sorted(called - component_members())


def test_every_bound_expression_resolves() -> None:
    html = read("index.html")
    bound = set(re.findall(r'x-text="(\w+)\(', html)) | set(re.findall(r'x-show="(\w+)\(', html))
    assert bound <= component_members(), sorted(bound - component_members())


def test_every_model_binding_has_backing_state() -> None:
    html = read("index.html")
    roots = set(re.findall(r'x-model(?:\.number)?="(\w+)', html))
    assert roots <= component_members(), sorted(roots - component_members())


# --- served correctly ---------------------------------------------------------


@pytest.mark.integration
async def test_the_api_serves_the_pwa_without_shadowing_itself(client: AsyncClient) -> None:
    """The static mount is registered last precisely so it cannot swallow /api."""
    assert (await client.get("/api/v1/ping")).status_code == 200

    shell = await client.get("/")
    assert shell.status_code == 200
    assert "sourdoughApp" in shell.text

    for path in ("/manifest.json", "/css/app.css", "/js/app.js", "/icons/icon-192.png"):
        assert (await client.get(path)).status_code == 200, path


@pytest.mark.integration
async def test_the_service_worker_is_not_cached_forever(client: AsyncClient) -> None:
    """A cached sw.js is how a PWA gets permanently stuck on an old release."""
    response = await client.get("/sw.js")
    assert response.status_code == 200
    assert "no-cache" in response.headers.get("cache-control", "")
    assert "javascript" in response.headers.get("content-type", "")
