(function () {
    'use strict';
    const motion = document.getElementById('display_reduce_motion');
    const ornament = document.getElementById('display_arabesques');
    const value = document.getElementById('display_arabesques_value');
    const legend = document.getElementById('display_legend');
    const scale = document.getElementById('display_scale');
    if (!motion || !ornament || !value || !legend || !scale) return;
    const key = 'trackerDisplayPreferences';
    let stored = {};
    try { stored = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (_) {}
    motion.checked = stored.reduceMotion === true;
    legend.checked = stored.showLegend !== false;
    if ([100, 115, 130].includes(stored.scale)) scale.value = String(stored.scale);
    if (Number.isInteger(stored.ornament) && stored.ornament >= 0 && stored.ornament <= 100) ornament.value = stored.ornament;
    function apply() {
        document.body.classList.toggle('reduce-motion', motion.checked);
        document.body.classList.toggle('hide-sidebar-legend', !legend.checked);
        document.documentElement.style.setProperty('--sidebar-ornament-opacity', String(Number(ornament.value) / 100));
        document.documentElement.style.zoom = String(Number(scale.value) / 100);
        value.textContent = ornament.value + ' %';
        try { localStorage.setItem(key, JSON.stringify({reduceMotion:motion.checked, showLegend:legend.checked, ornament:Number(ornament.value), scale:Number(scale.value)})); } catch (_) {}
    }
    motion.addEventListener('change', apply);
    legend.addEventListener('change', apply);
    scale.addEventListener('change', apply);
    ornament.addEventListener('input', apply);
    apply();
    const network = {
        hideIp: document.getElementById('steam_hide_ip'),
        showName: document.getElementById('steam_show_name'),
        showCountry: document.getElementById('steam_show_country'),
        showPing: document.getElementById('steam_show_ping')
    };
    if (Object.values(network).some(node => !node)) return;
    const networkKey = 'trackerSteamDisplayPreferences';
    let savedNetwork = {};
    try { savedNetwork = JSON.parse(localStorage.getItem(networkKey) || '{}') || {}; } catch (_) {}
    network.hideIp.checked = savedNetwork.hideIp === true;
    network.showName.checked = savedNetwork.showName !== false;
    network.showCountry.checked = savedNetwork.showCountry !== false;
    network.showPing.checked = savedNetwork.showPing !== false;
    function applyNetwork() {
        document.body.classList.toggle('hide-steam-address', network.hideIp.checked);
        document.body.classList.toggle('hide-steam-name', !network.showName.checked);
        document.body.classList.toggle('hide-steam-country', !network.showCountry.checked);
        document.body.classList.toggle('hide-steam-ping', !network.showPing.checked);
        try { localStorage.setItem(networkKey, JSON.stringify(Object.fromEntries(Object.entries(network).map(([name, node]) => [name, node.checked])))); } catch (_) {}
    }
    Object.values(network).forEach(node => node.addEventListener('change', applyNetwork));
    applyNetwork();
})();
