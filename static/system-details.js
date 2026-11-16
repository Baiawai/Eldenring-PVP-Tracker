(function () {
    'use strict';
    const formatBytes = value => {
        if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—';
        const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
        let index = 0;
        while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
        return new Intl.NumberFormat(document.documentElement.lang || undefined, {maximumFractionDigits:1}).format(value) + ' ' + units[index];
    };
    // Older running servers may still have a cached template without this row.
    document.querySelectorAll('.environment-details [data-details-environment]').forEach(rows => {
        if (rows.querySelector('.error-log-row')) return;
        const row = document.createElement('div'); row.className = 'environment-row error-log-row';
        row.innerHTML = '<span data-i18n="error_log_label">Journal des erreurs</span><strong><button type="button" class="error-log-link" data-error-log-open disabled>—</button><span class="error-log-status" data-error-log-status role="status"></span></strong>';
        rows.append(row);
    });
    function logMessage(key, fallback) { return window.uiT ? window.uiT(key, fallback) : fallback; }
    document.querySelectorAll('[data-error-log-open]').forEach(button => {
        button.addEventListener('click', async () => {
            const status = button.parentElement.querySelector('[data-error-log-status]');
            button.disabled = true;
            try {
                const response = await fetch('/error-log/open', {method:'POST', credentials:'same-origin'});
                const result = await response.json();
                if (!response.ok || !result.opened) throw new Error('open');
                status.textContent = '';
            } catch (_) {
                status.textContent = logMessage('error_log_open_failed', 'Impossible d’ouvrir le journal d’erreurs.');
            } finally { button.disabled = false; }
        });
    });
    const reporting = document.getElementById('error-reporting-enabled');
    const reportingStatus = document.getElementById('error-reporting-status');
    if (reporting) {
        fetch('/error-reporting', {credentials:'same-origin'}).then(response => {
            if (!response.ok) throw new Error('settings');
            return response.json();
        }).then(data => { reporting.checked = data.enabled; reporting.disabled = false; }).catch(() => {
            reportingStatus.textContent = logMessage('error_reporting_failed', 'Impossible de modifier le signalement des erreurs.');
        });
        reporting.addEventListener('change', async () => {
            const desired = reporting.checked;
            reporting.disabled = true;
            try {
                const response = await fetch('/error-reporting', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:desired})});
                if (!response.ok) throw new Error('settings');
                reporting.checked = (await response.json()).enabled;
                reportingStatus.textContent = '';
            } catch (_) {
                reporting.checked = !desired;
                reportingStatus.textContent = logMessage('error_reporting_failed', 'Impossible de modifier le signalement des erreurs.');
            } finally { reporting.disabled = false; }
        });
    }
    let request = null;
    async function refresh() {
        try {
            if (!request) request = fetch('/system-details').then(response => {
                if (!response.ok) throw new Error('system-details');
                return response.json();
            }).finally(() => { request = null; });
            const data = await request;
            if (data.request !== 'success') throw new Error('system-details');
            document.querySelectorAll('.environment-details').forEach(section => {
                section.querySelectorAll('[data-environment]').forEach(node => {
                    node.textContent = data.environment[node.dataset.environment] || '—';
                });
                const logButton = section.querySelector('[data-error-log-open]');
                const logStatus = section.querySelector('[data-error-log-status]');
                if (logButton && logStatus) {
                    const log = data.error_log;
                    logButton.textContent = log && log.path ? log.path : '—';
                    logButton.disabled = !(log && log.exists);
                    logStatus.textContent = log && !log.exists ? logMessage('error_log_missing', 'Aucun journal enregistré pour le moment.') : '';
                }
                window.uiSetStatus(section.querySelector('[data-details-status]'));
                section.querySelector('[data-details-environment]').hidden = false;
            });
            document.getElementById('storage_database_total').textContent = formatBytes(data.storage.database_bytes);
            document.getElementById('storage_disk_free').textContent = formatBytes(data.storage.disk_free_bytes);
            const list = document.getElementById('storage_databases'); list.replaceChildren();
            if (Array.isArray(data.storage.databases)) {
                data.storage.databases.forEach(item => {
                    const row = document.createElement('div'), name = document.createElement('span'), size = document.createElement('strong');
                    row.className = 'stat-detail-row'; name.textContent = item.name; size.textContent = formatBytes(item.bytes);
                    row.append(name, size); list.append(row);
                });
                if (!data.storage.databases.length) list.textContent = '—';
            } else list.textContent = '—';
            window.uiSetStatus(document.getElementById('storage_status'));
            document.getElementById('storage_content').hidden = false;
        } catch (_) {
            document.querySelectorAll('.environment-details').forEach(section => {
                window.uiSetStatus(section.querySelector('[data-details-status]'), 'stats_unavailable', 'Statistiques indisponibles.');
                section.querySelector('[data-details-environment]').hidden = true;
            });
            window.uiSetStatus(document.getElementById('storage_status'), 'stats_unavailable', 'Statistiques indisponibles.');
            document.getElementById('storage_content').hidden = true;
        }
    }
    document.querySelector('.btn_menu_settings[menu="6"]').addEventListener('click', refresh);
    document.getElementById('menu_button_information').addEventListener('click', () => {
        if (!document.getElementById('information_panel').hidden) refresh();
    });
    document.addEventListener('ui-language-change', () => {
        if (!document.getElementById('information_panel').hidden ||
            (document.getElementById('menu_button_settings').classList.contains('active') &&
             !document.querySelector('.contente_settings[setting="6"]').classList.contains('hide'))) refresh();
    });
})();
