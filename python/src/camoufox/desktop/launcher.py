from __future__ import annotations

import json
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit

from .mihomo import MihomoBinding, MihomoSupervisor
from .profiles import ProfileStore, launch_kwargs
from .socksbridge import SocksBridgeCredentialStore


SESSION_FILE_NAME = "desktop-tabs.json"
RESTORABLE_SCHEMES = {"file", "http", "https"}
PAGE_CHANGE_STABLE_POLLS = 2
OPEN_TAB_SCRIPT = "(url) => { window.open(url, '_blank'); }"


def ensure_fingerprint(profile: Dict[str, Any]) -> Dict[str, Any]:
    if profile.get("fingerprint_preset"):
        return profile

    from camoufox.fingerprints import get_random_preset

    preset = get_random_preset(os=profile.get("target_os") or None)
    if preset is None:
        raise RuntimeError("No bundled fingerprint presets are available")
    profile["fingerprint_preset"] = preset
    return profile


def wait_for_browser_close(
    context: Any,
    is_network_healthy: Optional[Callable[[], bool]] = None,
    on_pages_changed: Optional[Callable[[list[Any]], None]] = None,
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    notified_state = None
    pending_state = None
    stable_polls = 0
    while True:
        pages = [page for page in context.pages if not page.is_closed()]
        if pages and on_pages_changed is not None:
            state = tuple((id(page), str(page.url or "")) for page in pages)
            if notified_state is None:
                on_pages_changed(pages)
                notified_state = state
            elif state == notified_state:
                pending_state = None
                stable_polls = 0
            elif state != pending_state:
                pending_state = state
                stable_polls = 0
            else:
                stable_polls += 1
                if stable_polls >= PAGE_CHANGE_STABLE_POLLS:
                    on_pages_changed(pages)
                    notified_state = state
                    pending_state = None
                    stable_polls = 0
        if is_network_healthy is not None and not is_network_healthy():
            context.close()
            raise RuntimeError(
                "Mihomo stopped; the browser was closed to prevent a direct connection"
            )
        if not pages:
            return
        try:
            pages[0].wait_for_event("close", timeout=250)
        except PlaywrightTimeoutError:
            pass


def navigate_start_page(page: Any, start_url: str) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        page.goto(start_url, wait_until="commit")
    except PlaywrightTimeoutError:
        # A slow or unavailable home page must not close an otherwise healthy browser.
        pass


def open_tab_urls(pages: list[Any]) -> list[str]:
    urls = []
    for page in pages:
        url = str(page.url or "").strip()
        if urlsplit(url).scheme in RESTORABLE_SCHEMES:
            urls.append(url)
    return urls


def save_open_tabs(pages: list[Any], session_file: Path) -> list[str]:
    urls = open_tab_urls(pages)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema": 1, "urls": urls}, ensure_ascii=False, indent=2)
    descriptor, temporary = tempfile.mkstemp(
        prefix="desktop-tabs-",
        suffix=".json",
        dir=session_file.parent,
    )
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(payload)
            output.write("\n")
        os.replace(temporary, session_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return urls


def load_saved_tabs(session_file: Path) -> list[str]:
    if not session_file.exists():
        return []
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read saved browser tabs: {error}") from error
    urls = (
        data.get("urls")
        if isinstance(data, dict) and data.get("schema") == 1
        else None
    )
    if not isinstance(urls, list) or any(
        not isinstance(url, str) or urlsplit(url).scheme not in RESTORABLE_SCHEMES
        for url in urls
    ):
        raise ValueError("Invalid saved browser tabs")
    return urls


def restore_saved_tabs(first_page: Any, session_file: Path) -> bool:
    urls = load_saved_tabs(session_file)
    if not urls:
        return False
    navigate_start_page(first_page, urls[0])
    for url in urls[1:]:
        first_page.evaluate(OPEN_TAB_SCRIPT, url)
    return True


def _first_page(context: Any, timeout_ms: int = 15000) -> Any:
    """The startup about:blank page, waiting briefly if Playwright has not listed it yet."""
    import time

    pages = [page for page in context.pages if not page.is_closed()]
    if pages:
        return pages[0]

    wait_for_event = getattr(context, "wait_for_event", None)
    if wait_for_event is None:
        return context.new_page()

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        pages = [page for page in context.pages if not page.is_closed()]
        if pages:
            return pages[0]
        remaining_ms = (deadline - time.monotonic()) * 1000.0
        if remaining_ms <= 0:
            return context.new_page()
        try:
            return wait_for_event("page", timeout=min(250, remaining_ms))
        except PlaywrightTimeoutError:
            pass


def run_profile(
    store: ProfileStore,
    profile_id: str,
    on_started: Callable[[], None] = lambda: None,
    credential_store: Optional[SocksBridgeCredentialStore] = None,
    mihomo_supervisor: Optional[MihomoSupervisor] = None,
) -> None:
    from camoufox.sync_api import Camoufox

    profile = store.get(profile_id)
    if not profile.get("fingerprint_preset"):
        profile = store.save(ensure_fingerprint(profile))
    profile_dir = store.runtime_profile_dir(profile)
    profile_dir.mkdir(parents=True, exist_ok=True)
    session_file = profile_dir / SESSION_FILE_NAME

    with ExitStack() as stack:
        options = launch_kwargs(profile, profile_dir)
        network_health: Optional[Callable[[], bool]] = None
        socksbridge = profile.get("socksbridge") or {}
        if socksbridge.get("enabled"):
            credentials = credential_store or SocksBridgeCredentialStore()
            supervisor = mihomo_supervisor or MihomoSupervisor()
            token = credentials.get(socksbridge["credential_ref"])
            managed = stack.enter_context(
                supervisor.start(
                    MihomoBinding(
                        profile_id=profile_id,
                        host=socksbridge["host"],
                        node_id=socksbridge["node_id"],
                        token=token,
                    )
                )
            )
            options["proxy"] = managed.proxy
            # Only pass a verified exit IP. An empty string means lookup failed
            # after Mihomo was ready; skip GeoIP rather than aborting open.
            if profile.get("geoip", True) and managed.exit_ip:
                options["geoip"] = managed.exit_ip
            network_health = managed.is_healthy

        context = stack.enter_context(Camoufox(**options))
        # Persistent headed launches open about:blank without -silent. Wait for
        # that page instead of calling new_page() while pages is still empty —
        # a second window was briefly visible on slow Windows startups.
        page = _first_page(context)
        start_url = str(profile.get("start_url") or "").strip()
        if not restore_saved_tabs(page, session_file) and start_url:
            navigate_start_page(page, start_url)
        store.mark_opened(profile_id)
        on_started()
        last_saved_urls: Optional[list[str]] = None

        def persist_tabs(pages: list[Any]) -> None:
            nonlocal last_saved_urls
            urls = open_tab_urls(pages)
            if urls != last_saved_urls:
                last_saved_urls = save_open_tabs(pages, session_file)

        wait_for_browser_close(context, network_health, persist_tabs)
