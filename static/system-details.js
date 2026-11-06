(function () {
    'use strict';
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    const formatBytes = value => {
        if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—';
        const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
        let index = 0;
        while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
        return new Intl.NumberFormat(document.documentElement.lang || undefined, {maximumFractionDigits:1}).format(value) + ' ' + units[index];
    };
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
                section.querySelector('[data-details-status]').textContent = '';
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
            document.getElementById('storage_status').textContent = '';
            document.getElementById('storage_content').hidden = false;
        } catch (_) {
            document.querySelectorAll('.environment-details').forEach(section => {
                section.querySelector('[data-details-status]').textContent = tr('stats_unavailable', 'Statistiques indisponibles.');
                section.querySelector('[data-details-environment]').hidden = true;
            });
            document.getElementById('storage_status').textContent = tr('stats_unavailable', 'Statistiques indisponibles.');
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
