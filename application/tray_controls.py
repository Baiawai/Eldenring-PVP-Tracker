"""Notification-area controls share the application's normal monitor actions."""


def text(packs, language, key, fallback):
    return packs.get(language, {}).get('modern', {}).get(key, fallback)


def prepare_store_update(app, functions):
    """Wait until the capture thread has stopped at its own safe boundary."""
    return not functions.run_monitor and not functions.monitor_lock.locked()


def change_tracking(app, functions, store_update, icon, start, translate):
    if store_update.is_required():
        icon.notify(translate('store_update_message', 'Mets le tracker à jour pour continuer.'))
        return
    if bool(functions.run_monitor) == start:
        return
    try:
        with app.app_context():
            result = app.make_response(functions.start() if start else functions.stop())
        if result.status_code >= 400:
            raise RuntimeError('Monitor action failed')
    except Exception:
        app.logger.exception('Unable to change tracking from the notification area')
        icon.notify(translate('monitor_start_error' if start else 'tray_stop_error',
                              'Impossible de modifier le suivi.'))
