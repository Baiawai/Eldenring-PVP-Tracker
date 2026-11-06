(function () {
    'use strict';
    const labels = {
        statistics:['stats_title', 'Statistiques'], captures:['capture_page', 'Captures'],
        players:['menu_players', 'Joueurs'], history:['menu_history', 'Historique'],
        settings:['settings_page', 'Paramètres'], leaderboard:['leaderboard_title', 'Classement'],
        information:['information_title', 'Information']
    };
    const modes = {Arena:['arena', 'Arène 1v1'], Invasion:['invasion', 'Invasions'], Defense:['defense', 'Monde envahi']};
    const tr = (key, fallback) => {
        if (key === 'capture_page' || key === 'settings_page') {
            const pack = window.ELDEN_UI_PACKS && window.ELDEN_UI_PACKS[window.uiCurrentLanguage()];
            return pack ? pack.legacy[key === 'capture_page' ? 3 : 4] : fallback;
        }
        return window.uiT ? window.uiT(key, fallback) : fallback;
    };
    const number = n => new Intl.NumberFormat(document.documentElement.lang || undefined, {maximumFractionDigits:1}).format(n);
    const duration = seconds => seconds == null ? '—' : Math.floor(seconds / 3600) + ' h ' + Math.floor(seconds % 3600 / 60) + ' min';
    const put = (id, value) => { document.getElementById(id).textContent = value; };
    function row(container, label, value) {
        const div = document.createElement('div'), span = document.createElement('span'), strong = document.createElement('strong');
        div.className = 'stat-detail-row'; span.textContent = label; strong.textContent = value;
        div.append(span, strong); container.append(div);
    }
    async function refreshUsage() {
        const content = document.getElementById('usage_content');
        try {
            const [response, ...modeResponses] = await Promise.all([
                fetch('/usage-metrics'), ...Object.keys(modes).map(mode => fetch('/modeStats?mode=' + encodeURIComponent(mode)))
            ]);
            if (!response.ok) throw new Error('usage');
            const body = await response.json();
            if (body.request !== 'success') throw new Error('usage');
            const u = body.usage;
            put('usage_total', duration(u.total_seconds)); put('usage_sessions', number(u.sessions));
            put('usage_average', duration(u.average_seconds)); put('usage_streak', number(u.streak_days));
            const sessions = document.getElementById('usage_recent_sessions'); sessions.replaceChildren();
            u.recent_sessions.forEach(session => {
                const date = new Date(session.started);
                row(sessions, Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(document.documentElement.lang || undefined, {dateStyle:'medium', timeStyle:'short'}).format(date), duration(session.seconds));
            });
            if (!sessions.children.length) row(sessions, '—', '—');
            const features = document.getElementById('usage_features'); features.replaceChildren();
            Object.entries(u.features).filter(([name]) => labels[name]).sort((a,b) => b[1]-a[1]).forEach(([name,count]) => row(features, tr(...labels[name]), number(count)));
            if (!features.children.length) row(features, '—', '0');
            const modeData = await Promise.all(modeResponses.map(r => r.ok ? r.json() : null));
            const values = modeData.map(data => data && data.request === 'success' ? Math.max(0, Number(data.user[9]) || 0) : null);
            const total = values.reduce((sum, n) => sum + (n || 0), 0);
            const target = document.getElementById('usage_modes'); target.replaceChildren();
            Object.keys(modes).forEach((mode, index) => row(target, tr(...modes[mode]), values[index] === null ? '—' : number(values[index]) + (total && values.every(value => value !== null) ? ' · ' + number(100 * values[index] / total) + ' %' : '')));
            put('usage_status', ''); content.hidden = false;
        } catch (_) { content.hidden = true; put('usage_status', tr('stats_unavailable', 'Statistiques indisponibles.')); }
    }
    async function refreshDiagnostics() {
        try {
            const response = await fetch('/system-metrics'); if (!response.ok) throw new Error('diagnostics');
            const body = await response.json(), d = body.system;
            put('diag_cpu', d.cpu_percent == null ? '—' : number(d.cpu_percent) + ' %');
            put('diag_ram', d.memory_bytes == null ? '—' : number(d.memory_bytes / 1048576) + ' MiB');
            put('diag_ocr', d.ocr_count ? number(1000 * d.ocr_seconds / d.ocr_count) + ' ms' : '—');
            put('diag_ocr_errors', number(d.ocr_count) + ' / ' + number(d.ocr_errors));
            put('diag_errors', number(d.monitor_errors));
            put('diag_ping', d.steam_ping_ms == null ? '—' : number(d.steam_ping_ms) + ' ms (' + number(d.steam_peers_with_ping) + ')');
            const syncCount = d.sync_ok + d.sync_failed;
            put('diag_sync', number(d.sync_ok) + ' / ' + number(d.sync_failed));
            put('diag_sync_time', syncCount ? number(1000 * d.sync_seconds / syncCount) + ' ms' : '—');
            put('diag_version', d.version); put('diagnostics_status', ''); document.getElementById('diagnostics_content').hidden = false;
        } catch (_) { document.getElementById('diagnostics_content').hidden = true; put('diagnostics_status', tr('stats_unavailable', 'Statistiques indisponibles.')); }
    }
    const menu = {menu_button_info:'statistics', menu_button_captures:'captures', menu_button_players:'players', menu_button_history:'history', menu_button_settings:'settings', menu_button_multi:'leaderboard', menu_button_information:'information'};
    Object.entries(menu).forEach(([id, feature]) => {
        const button = document.getElementById(id); if (!button) return;
        button.addEventListener('click', () => {
            if (!button.classList.contains('active')) return;
            fetch('/usage-visit', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:'feature=' + encodeURIComponent(feature)}).catch(() => {});
        });
    });
    document.querySelector('.btn_menu_settings[menu="6"]').addEventListener('click', () => { refreshDiagnostics(); refreshUsage(); });
    setInterval(() => {
        const panel = document.querySelector('.contente_settings[setting="6"]');
        if (document.getElementById('menu_button_settings').classList.contains('active') && !panel.classList.contains('hide')) refreshDiagnostics();
    }, 5000);
    document.addEventListener('ui-language-change', () => {
        const panel = document.querySelector('.contente_settings[setting="6"]');
        if (document.getElementById('menu_button_settings').classList.contains('active') && !panel.classList.contains('hide')) refreshUsage();
    });
})();
