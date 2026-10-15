from __future__ import annotations

from contextlib import ExitStack
from typing import Any, Callable, Dict, Optional

from .mihomo import MihomoBinding, MihomoSupervisor
from .profiles import ProfileStore, launch_kwargs
from .socksbridge import SocksBridgeCredentialStore


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
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    while True:
        if is_network_healthy is not None and not is_network_healthy():
            context.close()
            raise RuntimeError(
                "Mihomo stopped; the browser was closed to prevent a direct connection"
            )
        pages = [page for page in context.pages if not page.is_closed()]
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
        if start_url:
            navigate_start_page(page, start_url)
        store.mark_opened(profile_id)
        on_started()
        wait_for_browser_close(context, network_health)
