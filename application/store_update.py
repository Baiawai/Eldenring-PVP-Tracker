"""Check for updates offered by Microsoft Store to the installed Store package."""
import asyncio
import logging
import math
import threading
from typing import NamedTuple, Optional

from flask import jsonify, render_template

from application.browser_language import browser_language
from application.runtime_paths import FROZEN
from application.version import APP_VERSION

STORE_FAMILY = 'Baiawai.EldenRingPvPTracker_edd608y7v4rk6'
STORE_URL = 'ms-windows-store://pdp/?productid=9P7J2LSRPPTF'
_REQUIRED = False
_PENDING = False
_AVAILABLE_VERSION = None
_AVAILABLE_VERSION_SOURCE = None
_METADATA_STARTED = False
_METADATA_LOOKUP_PENDING = False
_STATE_LOCK = threading.Lock()
_CHECK_LOCK = threading.Lock()
_PERIODIC_START_LOCK = threading.Lock()
_PERIODIC_STARTED = False
_LOGGER = logging.getLogger(__name__)


class _StoreUpdateResult(NamedTuple):
    available: bool
    version: Optional[str]

    def __bool__(self):
        return self.available


def _normalize_result(value):
    # Preserve compatibility with callers and tests returning only a boolean.
    if isinstance(value, _StoreUpdateResult):
        return value
    return _StoreUpdateResult(bool(value), None)


def _newer_version_text(value):
    """Accept only a canonical numeric version newer than this installation."""
    if not isinstance(value, str):
        return None
    pieces = value.split('.')
    if len(pieces) != 4 or any(not p.isascii() or not p.isdigit() or len(p) > 5 for p in pieces):
        return None
    try:
        parsed = tuple(int(part) for part in pieces)
        installed = tuple(int(part) for part in APP_VERSION.split('.'))
    except (TypeError, ValueError):
        return None
    if len(installed) != 4 or any(part > 65535 for part in parsed) or parsed <= installed:
        return None
    return '.'.join(str(part) for part in parsed)


def _start_indicative_version_lookup():
    """Ask the optional private provider once, after Store confirmation only."""
    global _METADATA_STARTED, _METADATA_LOOKUP_PENDING
    with _STATE_LOCK:
        if not (_REQUIRED or _PENDING) or _AVAILABLE_VERSION is not None or _METADATA_STARTED:
            return False
        _METADATA_STARTED = True
        _METADATA_LOOKUP_PENDING = True

    def lookup():
        global _AVAILABLE_VERSION, _AVAILABLE_VERSION_SOURCE, _METADATA_LOOKUP_PENDING
        version = None
        try:
            from application._private_store_version import fetch_version
            version = _newer_version_text(fetch_version(APP_VERSION, timeout=3.0))
        except Exception:
            # This optional provider never determines Store availability.
            pass
        finally:
            with _STATE_LOCK:
                if (_REQUIRED or _PENDING) and _AVAILABLE_VERSION is None and version:
                    _AVAILABLE_VERSION = version
                    _AVAILABLE_VERSION_SOURCE = 'site'
                _METADATA_LOOKUP_PENDING = False

    try:
        threading.Thread(target=lookup, name='store-update-version', daemon=True).start()
    except Exception:
        with _STATE_LOCK:
            _METADATA_LOOKUP_PENDING = False
        return False
    return True


def _is_store_package(package):
    """A frozen executable alone is not evidence of Store distribution."""
    return (int(package.signature_kind) == 3 and
            package.id.family_name.casefold() == STORE_FAMILY.casefold())


def _main_package_update(package, updates):
    """Keep only updates for our package and select the highest known version."""
    if not _is_store_package(package):
        return _StoreUpdateResult(False, None)
    family = package.id.family_name.casefold()
    found = False
    highest = None
    try:
        installed = tuple(int(part) for part in APP_VERSION.split('.'))
        if len(installed) != 4 or any(not 0 <= part <= 65535 for part in installed):
            installed = None
    except (TypeError, ValueError):
        installed = None
    for update in updates:
        try:
            identity = update.package.id
            if identity.family_name.casefold() != family:
                continue
        except (AttributeError, TypeError):
            continue
        found = True
        try:
            version = identity.version
            parts = (version.major, version.minor, version.build, version.revision)
            if any(type(part) is not int or not 0 <= part <= 65535 for part in parts):
                continue
        except (AttributeError, TypeError, ValueError):
            continue
        # StorePackageUpdate.Package can identify the installed package rather
        # than the offered build. Never present that as the newer version.
        if installed is None or parts <= installed:
            continue
        if highest is None or parts > highest:
            highest = parts
    return _StoreUpdateResult(found, '.'.join(str(part) for part in highest) if highest is not None else None)


def _has_main_package_update(package, updates):
    return bool(_main_package_update(package, updates))


def _query_store_update():
    # Desktop Bridge apps must associate StoreContext with a window owned by
    # the thread making the request, even though this application has no GUI.
    import win32api
    import win32gui
    import winrt.runtime
    import winrt.windows.foundation
    import winrt.windows.foundation.collections
    import winrt.windows.storage.streams
    from winrt.runtime.interop import initialize_with_window
    from winrt.windows.applicationmodel import Package
    from winrt.windows.services.store import StoreContext

    winrt.runtime.init_apartment(winrt.runtime.ApartmentType.SINGLE_THREADED)
    hwnd = None
    package = None
    context = None
    try:
        package = Package.current
        if not _is_store_package(package):
            return False
        hwnd = win32gui.CreateWindowEx(0, 'STATIC', '', 0, 0, 0, 0, 0,
                                      0, 0, win32api.GetModuleHandle(None), None)
        context = StoreContext.get_default()
        initialize_with_window(context, hwnd)

        async def query():
            operation = context.get_app_and_optional_store_package_updates_async()
            updates = await asyncio.wait_for(operation, timeout=8)
            return _main_package_update(package, updates)

        return asyncio.run(query())
    finally:
        context = None
        package = None
        if hwnd:
            win32gui.DestroyWindow(hwnd)
        winrt.runtime.uninit_apartment()


def check_at_start(timeout=10):
    """Bound startup time; an unavailable Store must never prevent offline use."""
    global _REQUIRED, _AVAILABLE_VERSION, _AVAILABLE_VERSION_SOURCE
    if is_required():
        return True
    if not FROZEN:
        return False
    result = []
    finished = threading.Event()

    def check():
        try:
            # A timed-out Store call can outlive its caller. Never overlap it
            # with a later periodic check, even if the native API gets stuck.
            if not _CHECK_LOCK.acquire(blocking=False):
                return
            try:
                result.append(_normalize_result(_query_store_update()))
            finally:
                _CHECK_LOCK.release()
        except Exception:
            result.append(False)
        finally:
            finished.set()

    threading.Thread(target=check, name='store-update-check', daemon=True).start()
    if finished.wait(timeout) and result and result[0]:
        with _STATE_LOCK:
            _REQUIRED = True
            _AVAILABLE_VERSION = result[0].version
            _AVAILABLE_VERSION_SOURCE = 'store' if result[0].version else None
        if result[0].version is None:
            _start_indicative_version_lookup()
    return is_required()


def is_required():
    with _STATE_LOCK:
        return _REQUIRED


def is_pending():
    """A Store update is confirmed, but an active fight may still finish."""
    with _STATE_LOCK:
        return _PENDING


def available_version():
    """Return the displayed version, which may be indicative; see its source."""
    with _STATE_LOCK:
        return _AVAILABLE_VERSION


def get_version_status():
    """Display-only status; this endpoint never triggers a network request."""
    with _STATE_LOCK:
        if not (_REQUIRED or _PENDING):
            return {'available_version': None, 'version_source': None, 'lookup_pending': False}
        return {'available_version': _AVAILABLE_VERSION,
                'version_source': _AVAILABLE_VERSION_SOURCE,
                'lookup_pending': _METADATA_LOOKUP_PENDING}


def _check_periodic_once():
    """Detect an update without blocking the caller on an overlapping query."""
    global _PENDING, _AVAILABLE_VERSION, _AVAILABLE_VERSION_SOURCE
    if not FROZEN:
        return False
    with _STATE_LOCK:
        if _REQUIRED or _PENDING:
            return True
    if not _CHECK_LOCK.acquire(blocking=False):
        return False
    try:
        try:
            result = _normalize_result(_query_store_update())
        except Exception:
            return False
    finally:
        _CHECK_LOCK.release()
    if result:
        with _STATE_LOCK:
            if not _REQUIRED:
                _PENDING = True
                _AVAILABLE_VERSION = result.version
                _AVAILABLE_VERSION_SOURCE = 'store' if result.version else None
        if result.version is None:
            _start_indicative_version_lookup()
    return bool(result)


def _periodic_worker(interval, prepare_block, stop_event):
    global _PENDING, _REQUIRED
    while not stop_event.wait(interval):
        if is_required():
            return
        if not _check_periodic_once():
            continue
        failure_logged = False
        while is_pending() and not is_required():
            try:
                ready = bool(prepare_block())
                failure_logged = False
            except Exception:
                ready = False
                if not failure_logged:
                    _LOGGER.exception('Unable to prepare the required Store update')
                    failure_logged = True
            if ready:
                with _STATE_LOCK:
                    if _PENDING:
                        _REQUIRED = True
                        _PENDING = False
                return
            if stop_event.wait(1):
                return


def start_periodic_check(interval=600, prepare_block=None):
    """Start one background Store checker; never affect non-Store dev runs."""
    global _PERIODIC_STARTED
    if not FROZEN:
        return False
    if not callable(prepare_block):
        raise ValueError('A Store update preparation callback is required')
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('Invalid Store update interval')
    with _PERIODIC_START_LOCK:
        if _PERIODIC_STARTED or is_required():
            return False
        thread = threading.Thread(target=_periodic_worker,
                                  args=(interval, prepare_block, threading.Event()),
                                  name='store-update-periodic', daemon=True)
        thread.start()
        _PERIODIC_STARTED = True
    return True


def gate_response(request, selected_language, all_packs):
    """Prevent local operations when a Store update has been confirmed."""
    if (not _REQUIRED or request.path.startswith('/static/') or request.path == '/exit' or
            (request.path == '/store-update-status' and request.method == 'GET')):
        return None
    if request.path == '/' and request.method in ('GET', 'HEAD'):
        try:
            language = selected_language()
        except Exception:
            language = None
        if not language:
            language = browser_language(request.accept_languages)
        pack = all_packs().get(language, {})
        text = pack.get('modern', {})
        french = language == 'fra'
        status = get_version_status()
        return render_template('store-update.html',
            language='fr' if french else pack.get('html_lang', 'en'),
            title=text.get('store_update_title', 'Mise à jour requise' if french else 'Update required'),
            message=text.get('store_update_message', 'Une nouvelle version est disponible. Mets le tracker à jour depuis le Microsoft Store pour continuer.' if french else 'A new version is available. Update the tracker in Microsoft Store to continue.'),
            instruction=text.get('store_update_instruction', 'Le bouton ouvre le Microsoft Store et ferme le tracker. Installe la mise à jour, puis relance le tracker.' if french else 'The button opens Microsoft Store and closes the tracker. Install the update, then restart the tracker.'),
            action=text.get('store_update_action', 'Ouvrir le Microsoft Store' if french else 'Open Microsoft Store'),
            current_version=APP_VERSION,
            available_version=status['available_version'],
            available_version_source=status['version_source'],
            current_version_label=text.get('store_update_current_version', 'Version actuelle' if french else 'Installed version'),
            new_version_label=text.get('store_update_new_version', 'Nouvelle version' if french else 'New version'),
            unavailable_label=text.get('store_update_version_unavailable', 'Indisponible' if french else 'Unavailable'),
            indicative_version_label=text.get('store_update_latest_published_indicative', 'Dernière version publiée (indicative)' if french else 'Latest published version (indicative)'),
            store_url=STORE_URL)
    return jsonify(error='store_update_required'), 423
