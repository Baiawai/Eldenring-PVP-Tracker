"""Check for updates offered by Microsoft Store to the installed Store package."""
import asyncio
import threading

from flask import jsonify, render_template

from application.browser_language import browser_language
from application.runtime_paths import FROZEN

STORE_FAMILY = 'Baiawai.EldenRingPvPTracker_edd608y7v4rk6'
STORE_URL = 'ms-windows-store://pdp/?productid=9P7J2LSRPPTF'
_REQUIRED = False


def _is_store_package(package):
    """A frozen executable alone is not evidence of Store distribution."""
    return (int(package.signature_kind) == 3 and
            package.id.family_name.casefold() == STORE_FAMILY.casefold())


def _has_main_package_update(package, updates):
    if not _is_store_package(package):
        return False
    family = package.id.family_name.casefold()
    return any(update.package.id.family_name.casefold() == family for update in updates)


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
            return _has_main_package_update(package, updates)

        return asyncio.run(query())
    finally:
        context = None
        package = None
        if hwnd:
            win32gui.DestroyWindow(hwnd)
        winrt.runtime.uninit_apartment()


def check_at_start(timeout=10):
    """Bound startup time; an unavailable Store must never prevent offline use."""
    global _REQUIRED
    _REQUIRED = False
    if not FROZEN:
        return False
    result = []
    finished = threading.Event()

    def check():
        try:
            result.append(bool(_query_store_update()))
        except Exception:
            result.append(False)
        finally:
            finished.set()

    threading.Thread(target=check, name='store-update-check', daemon=True).start()
    if finished.wait(timeout):
        _REQUIRED = bool(result and result[0])
    return _REQUIRED


def is_required():
    return _REQUIRED


def gate_response(request, selected_language, all_packs):
    """Prevent local operations when a Store update was confirmed at startup."""
    if not _REQUIRED or request.path.startswith('/static/') or request.path == '/exit':
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
        return render_template('store-update.html',
            language='fr' if french else pack.get('html_lang', 'en'),
            title=text.get('store_update_title', 'Mise à jour requise' if french else 'Update required'),
            message=text.get('store_update_message', 'Une nouvelle version est disponible. Mets le tracker à jour depuis le Microsoft Store pour continuer.' if french else 'A new version is available. Update the tracker in Microsoft Store to continue.'),
            instruction=text.get('store_update_instruction', 'Ouvre le Microsoft Store, quitte le tracker depuis son icône dans la zone de notification, puis mets-le à jour et relance-le.' if french else 'Open Microsoft Store, quit the tracker from its notification-area icon, update it, then restart it.'),
            action=text.get('store_update_action', 'Ouvrir le Microsoft Store' if french else 'Open Microsoft Store'),
            store_url=STORE_URL)
    return jsonify(error='store_update_required'), 423
