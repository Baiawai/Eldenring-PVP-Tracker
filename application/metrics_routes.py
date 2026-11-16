"""Read local usage and current diagnostics; no game data leaves the PC."""
from __main__ import app
from flask import jsonify, request
from application import usage_metrics, peer_tracking, system_details, error_log, tracker_presence, error_reports
from application.version import APP_VERSION


@app.route('/usage-metrics', methods=['GET'])
def usage_metrics_get():
    try:
        return jsonify(request='success', usage=usage_metrics.usage())
    except Exception:
        app.logger.exception('Unable to read usage metrics')
        return jsonify(request='error'), 503


@app.route('/usage-visit', methods=['POST'])
def usage_metrics_visit():
    feature = request.form.get('feature', '')
    if feature not in usage_metrics.FEATURES:
        return jsonify(request='error'), 400
    try:
        usage_metrics.visit(feature)
        return jsonify(request='success')
    except Exception:
        app.logger.exception('Unable to save usage visit')
        return jsonify(request='error'), 503


@app.route('/system-metrics', methods=['GET'])
def system_metrics_get():
    result = usage_metrics.system()
    with peer_tracking._lock:
        peers = list(peer_tracking._snapshot.get('peers', []))
    pings = [p['ping'] for p in peers if isinstance(p.get('ping'), (int, float)) and not isinstance(p['ping'], bool) and 0 <= p['ping'] < 60000]
    result['steam_ping_ms'] = sum(pings) / len(pings) if pings else None
    result['steam_peers_with_ping'] = len(pings)
    result['version'] = APP_VERSION
    return jsonify(request='success', system=result)


@app.route('/system-details', methods=['GET'])
def system_details_get():
    return jsonify(request='success', **system_details.snapshot())


@app.route('/error-log/open', methods=['POST'])
def error_log_open():
    opened = error_log.open_log()
    return jsonify(opened=opened), 200 if opened else 404


@app.route('/tracker-presence/active', methods=['POST'])
def tracker_presence_active():
    tracker_presence.notify_browser()
    return '', 204


@app.route('/error-reporting', methods=['GET', 'POST'])
def error_reporting_settings():
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or type(data.get('enabled')) is not bool:
                return jsonify(request='error'), 400
            error_reports.set_enabled(data['enabled'])
        return jsonify(request='success', enabled=error_reports.enabled())
    except Exception:
        app.logger.exception('Unable to access diagnostic settings')
        return jsonify(request='error'), 503
