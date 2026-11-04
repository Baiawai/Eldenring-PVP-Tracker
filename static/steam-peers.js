(function () {
    const list = document.getElementById('steam_peer_list');
    const status = document.getElementById('steam_peer_status');
    const profileStatus = document.getElementById('steam_profile_status');
    const settingsStatus = document.getElementById('steam_settings_status');
    const enabled = document.getElementById('steam_peer_enabled');
    const pingStatus = document.getElementById('steam_ping_status');
    const pingButton = document.getElementById('steam_ping_activate');
    let state = null;
    let pingPending = false;
    function tr(key, fallback) { return window.uiT ? window.uiT(key, fallback) : fallback; }
    function message(name) {
        return ({
            starting: tr('steam_starting', 'Connexion à Steam…'),
            game_closed: tr('steam_game_closed', 'Lance Elden Ring pour détecter les joueurs.'),
            waiting_log: tr('steam_waiting_log', 'Active le journal Steam dans les paramètres P2P.'),
            steam_unavailable: tr('steam_unavailable', 'Steam est indisponible ou non connecté.'),
            helper_error: tr('steam_error', 'La connexion à Steam a échoué.'),
            disabled: tr('steam_off', 'Détection désactivée.'),
            active: tr('steam_empty', 'Aucun autre joueur détecté.')
        })[name] || tr('steam_error', 'La connexion à Steam a échoué.');
    }
    function render() {
        if (!state) return;
        list.replaceChildren();
        const peers = Array.isArray(state.peers) ? state.peers : [];
        settingsStatus.textContent = state.status === 'active' ? tr('detection_enabled', 'Détection activée') : message(state.status);
        if (state.status === 'waiting_log') document.getElementById('steam_manual_setup').open = true;
        enabled.value = state.enabled ? 'true' : 'false';
        if (['active', 'unavailable', 'denied'].includes(state.ping_mode)) pingPending = false;
        const pingMessages = {
            active: tr('steam_ping_active', 'Mesure avancée des pings active.'),
            unavailable: tr('steam_ping_unavailable', 'La mesure réseau Windows est indisponible.'),
            denied: tr('steam_ping_denied', 'Autorisation administrateur refusée ou mesure indisponible.'),
            requesting: tr('steam_ping_requesting', 'Confirme la demande administrateur Windows.'),
            admin_required: tr('steam_ping_required', 'Mesure avancée désactivée.')
        };
        const pingMessage = pingPending ? pingMessages.requesting : (pingMessages[state.ping_mode] || pingMessages.admin_required);
        const p2pReady = state.status === 'active' && state.ping_mode === 'active' && !pingPending;
        status.textContent = state.status !== 'active' ? message(state.status) :
            (peers.length === 0 ? message('active') : (p2pReady ? '' : pingMessage));
        status.classList.toggle('steam-empty', state.status === 'starting' || (state.status === 'active' && peers.length === 0));
        pingStatus.textContent = pingMessage;
        pingButton.disabled = pingPending || state.ping_mode === 'active' || state.ping_mode === 'requesting';
        peers.forEach(function(peer) {
            const item = document.createElement('li');
            const row = document.createElement('div');
            const name = document.createElement('button');
            const ping = document.createElement('span');
            const ip = document.createElement('div');
            row.className = 'steam-peer-row';
            name.type = 'button';
            name.className = 'steam-peer-name';
            name.textContent = peer.name || peer.id;
            name.title = tr('steam_profile_open', 'Ouvrir le profil dans Steam');
            name.addEventListener('click', async function() {
                profileStatus.textContent = '';
                try {
                    const response = await fetch('/steam-profile', {method:'POST', body:new URLSearchParams({steam_id:peer.id})});
                    if (!response.ok) throw new Error('request');
                    profileStatus.textContent = tr('steam_profile_sent', 'Profil demandé : reviens dans le jeu pour voir Steam.');
                } catch (_) { profileStatus.textContent = tr('steam_profile_error', 'Impossible d’ouvrir ce profil Steam.'); }
            });
            ping.className = 'steam-peer-ping';
            ping.textContent = typeof peer.ping === 'number' && peer.ping >= 0 ? Math.round(peer.ping) + ' ms' : '—';
            ip.className = 'steam-peer-ip';
            const label = peer.relay ? tr('steam_ip_relay', 'Relais') : tr('steam_ip_label', 'IP réseau');
            ip.textContent = label + ' : ' + (peer.ip || '—');
            if (peer.ip) window.appendIpCountry(ip, peer.country_code);
            row.append(name, ping); item.append(row, ip); list.append(item);
        });
    }
    async function refresh() {
        try {
            const r = await fetch('/steam-peers', {cache:'no-store'});
            if (!r.ok) throw new Error('request');
            state = await r.json(); render();
        } catch (_) { state = {status:'helper_error', peers:[], enabled:true}; render(); }
    }
    enabled.addEventListener('change', async function() {
        enabled.disabled = true;
        try {
            const r = await fetch('/steam-peers', {method:'POST', body:new URLSearchParams({enabled:enabled.value})});
            if (!r.ok) throw new Error('request');
            state = await r.json(); render();
        } catch (_) { settingsStatus.textContent = message('helper_error'); }
        finally { enabled.disabled = false; }
    });
    pingButton.addEventListener('click', async function() {
        pingButton.disabled = true;
        try {
            const r = await fetch('/steam-ping', {method:'POST'});
            if (!r.ok) throw new Error('request');
            pingPending = true;
            pingStatus.textContent = tr('steam_ping_requesting', 'Confirme la demande administrateur Windows.');
            setTimeout(function() { pingPending = false; refresh(); }, 30000);
        } catch (_) {
            pingPending = false;
            pingStatus.textContent = tr('steam_ping_start_game', 'Lance le jeu et active la détection Steam avant de continuer.');
            pingButton.disabled = false;
        }
    });
    document.getElementById('steam_copy_command').addEventListener('click', async function() {
        try { await navigator.clipboard.writeText(document.getElementById('steam_command').textContent); settingsStatus.textContent = tr('steam_copied', 'Commande copiée.'); }
        catch (_) { settingsStatus.textContent = tr('steam_copy_error', 'Sélectionne et copie la commande.'); }
    });
    document.addEventListener('ui-language-change', render);
    refresh(); setInterval(refresh, 3000);
})();
