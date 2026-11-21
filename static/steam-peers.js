(function () {
    const list = document.getElementById('steam_peer_list');
    const status = document.getElementById('steam_peer_status');
    const profileStatus = document.getElementById('steam_profile_status');
    const settingsStatus = document.getElementById('steam_settings_status');
    const enabled = document.getElementById('steam_peer_enabled');
    const pingStatus = document.getElementById('steam_ping_status');
    const pingButton = document.getElementById('steam_ping_activate');
    const pingHelp = document.getElementById('steam_ping_help');
    const storeBuild = document.body.dataset.storeBuild === 'true';
    if (storeBuild) { pingButton.hidden = true; pingHelp.hidden = true; }
    const host = document.createElement('p');
    host.className = 'steam-world-host';
    host.hidden = true;
    status.before(host);
    let state = null;
    let pingPending = false;
    let playerOptions = Object.assign({}, window.trackerOverlayOptions || {});
    const optionDefaults = {show_steam_id:false, show_jitter:false, show_ping_average:false,
                            show_quality:false, show_player_count:false};
    const cards = new Map();
    function tr(key, fallback) { return window.uiT ? window.uiT(key, fallback) : fallback; }
    function visible(key) {
        return typeof playerOptions[key] === 'boolean' ? playerOptions[key] : optionDefaults[key] !== false;
    }
    function formatDuration(value) {
        if (!Number.isFinite(value) || value < 0 || value > 86400 * 365) return '';
        const seconds = Math.floor(value);
        const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, s = seconds % 60;
        return [h, m, s].map(n => String(n).padStart(2, '0')).join(':');
    }
    function createCard(id) {
        const item = document.createElement('li');
        item.className = 'steam-peer-item';
        item.dataset.steamId = id;
        const identity = document.createElement('div'); identity.className = 'steam-peer-identity';
        const avatar = document.createElement('div');
        avatar.className = 'steam-peer-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        const fallback = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        fallback.setAttribute('viewBox', '0 0 64 64');
        fallback.innerHTML = '<circle cx="32" cy="23" r="12"/><path d="M10 58c1-13 9-20 22-20s21 7 22 20z"/>';
        avatar.append(fallback);
        const info = document.createElement('div'); info.className = 'steam-peer-info';
        const heading = document.createElement('div'); heading.className = 'steam-peer-heading';
        const name = document.createElement('button'); name.type = 'button'; name.className = 'steam-peer-name';
        const badge = document.createElement('span'); badge.className = 'steam-peer-host';
        const role = document.createElement('div'); role.className = 'steam-peer-role';
        const steamId = document.createElement('div'); steamId.className = 'steam-peer-id';
        const encounters = document.createElement('div'); encounters.className = 'steam-peer-encounters';
        const country = document.createElement('div'); country.className = 'steam-peer-country';
        const network = document.createElement('div'); network.className = 'steam-peer-network';
        const ping = document.createElement('span'); ping.className = 'steam-peer-ping';
        const quality = document.createElement('span'); quality.className = 'steam-peer-quality';
        const details = document.createElement('div'); details.className = 'steam-peer-details';
        const duration = document.createElement('span'); duration.className = 'steam-peer-duration';
        const average = document.createElement('span'); average.className = 'steam-peer-ping-detail';
        const jitter = document.createElement('span'); jitter.className = 'steam-peer-jitter';
        details.append(duration, average, jitter);
        identity.append(avatar);
        heading.append(name, ping); network.append(quality);
        info.append(heading, badge, role, steamId, details, network, encounters); item.append(identity, info, country);
        name.addEventListener('click', async function() {
            window.uiSetStatus(profileStatus);
            try {
                const response = await fetch('/steam-profile', {method:'POST', body:new URLSearchParams({steam_id:item.dataset.steamId})});
                if (!response.ok) throw new Error('request');
                window.uiSetStatus(profileStatus, 'steam_profile_sent', 'Profil demandé : reviens dans le jeu pour voir Steam.');
            } catch (_) { window.uiSetStatus(profileStatus, 'steam_profile_error', 'Impossible d’ouvrir ce profil Steam.'); }
        });
        item._peerNodes = {identity, avatar, info, name, badge, role, steamId, ping, quality, country,
                           details, duration, average, jitter, encounters};
        item._avatarState = {wanted:null, loaded:null, pending:false, nextTry:0, token:0};
        return item;
    }
    function renderCard(item, peer) {
        const n = item._peerNodes;
        n.identity.hidden = !visible('show_avatars');
        n.name.hidden = !visible('show_player_name');
        n.ping.hidden = !visible('show_ping');
        n.country.hidden = !visible('show_country');
        n.name.textContent = peer.name && peer.name !== peer.id ? peer.name : tr('steam_world_host_unknown', 'Non identifié');
        n.name.title = tr('steam_profile_open', 'Ouvrir le profil dans Steam');
        n.badge.hidden = !(state.world_host && state.world_host.peer_id && peer.id === state.world_host.peer_id);
        n.badge.textContent = tr('steam_host_probable', 'Hôte');
        const roles = {ally:['ally', 'Allié'], cooperator:['enemy_cooperator', 'Allié adverse'],
                       hunter:['hunter', 'Chasseur'], invader:['invader', 'Envahisseur'], duelist:['duelist', 'Duelliste']};
        const role = typeof peer.role === 'string' && Object.prototype.hasOwnProperty.call(roles, peer.role) ? roles[peer.role] : null;
        n.role.hidden = !visible('show_role') || !role;
        n.role.textContent = role ? tr(role[0], role[1]) : '';
        n.steamId.hidden = !visible('show_steam_id');
        n.steamId.textContent = 'SteamID : ' + peer.id;
        const ping = Number.isFinite(peer.ping) && peer.ping >= 0 && peer.ping <= 60000 ? Math.round(peer.ping) : null;
        n.ping.textContent = ping === null ? '—' : ping + ' ms';
        const pingClass = ping === null ? 'unknown' : peer.ping < 100 ? 'good' : peer.ping < 180 ? 'fair' : 'poor';
        n.ping.className = 'steam-peer-ping is-' + pingClass;
        const quality = Number.isFinite(peer.quality) && peer.quality >= 0 && peer.quality <= 1 ? peer.quality : null;
        const qualityClass = quality === null ? 'unknown' : quality >= .9 ? 'good' : quality >= .7 ? 'fair' : 'poor';
        n.quality.className = 'steam-peer-quality is-' + qualityClass;
        n.quality.hidden = !visible('show_quality');
        n.quality.textContent = quality === null ? tr('steam_peer_quality_unknown', 'Qualité de connexion indisponible') :
            tr('steam_peer_connection_quality', 'Qualité de connexion') + ' : ' + Math.round(quality * 100) + ' %';
        n.country.replaceChildren(); window.appendIpCountry(n.country, peer.country_code);
        n.duration.hidden = !visible('show_duration');
        n.duration.textContent = tr('steam_peer_duration', 'Connexion') + ' : ' + (formatDuration(peer.connected_seconds) || '—');
        n.average.hidden = !visible('show_ping_average');
        n.average.textContent = tr('steam_peer_ping_average', 'Ping moyen') + ' : ' +
            (Number.isFinite(peer.average_ping) && peer.average_ping >= 0 && peer.average_ping <= 60000 ? Math.round(peer.average_ping) + ' ms' : '—');
        n.jitter.hidden = !visible('show_jitter');
        n.jitter.textContent = tr('steam_peer_jitter', 'Jitter') + ' : ' +
            (Number.isFinite(peer.jitter) && peer.jitter >= 0 && peer.jitter <= 60000 ? Math.round(peer.jitter) + ' ms' : '—');
        n.details.hidden = n.duration.hidden && n.average.hidden && n.jitter.hidden;
        n.encounters.hidden = !visible('show_player_stats');
        const count = Number.isSafeInteger(peer.encounters) && peer.encounters >= 0 ? peer.encounters : '—';
        n.encounters.textContent = tr('overlay_encounter_count', 'Nombre de rencontres') + ' : ' + count;
        // Read only the local cache. A new revision triggers one refresh;
        // failed requests retry at most every 30 seconds, never on every ping.
        const available = visible('show_avatars') && peer.avatar_available === true && /^\d{17}$/.test(peer.id);
        const avatarState = item._avatarState;
        if (!available) {
            avatarState.wanted = avatarState.loaded = null;
            avatarState.pending = false; avatarState.nextTry = 0; avatarState.token++;
            n.avatar.querySelectorAll('img').forEach(img => img.remove());
            n.avatar.classList.remove('has-image');
        } else {
            const revision = Number.isSafeInteger(peer.avatar_revision) && peer.avatar_revision > 0
                ? String(peer.avatar_revision) : 'legacy';
            if (avatarState.wanted !== revision) {
                avatarState.wanted = revision;
                avatarState.nextTry = 0;
            }
            if (avatarState.loaded !== revision && !avatarState.pending && Date.now() >= avatarState.nextTry) {
                const img = document.createElement('img'); img.alt = '';
                const token = ++avatarState.token;
                avatarState.pending = true;
                img.addEventListener('error', function() {
                    if (token !== avatarState.token) return;
                    avatarState.pending = false;
                    avatarState.nextTry = Date.now() + 30000;
                });
                img.addEventListener('load', function() {
                    if (token !== avatarState.token) return;
                    avatarState.pending = false;
                    if (avatarState.wanted !== revision) return;
                    n.avatar.querySelectorAll('img').forEach(old => old.remove());
                    n.avatar.append(img);
                    n.avatar.classList.add('has-image');
                    avatarState.loaded = revision;
                    avatarState.nextTry = 0;
                });
                img.src = '/steam-peer-avatar/' + peer.id + '?revision=' + encodeURIComponent(revision);
            }
        }
    }
    function message(name) {
        return ({
            starting: tr('steam_starting', 'Connexion à Steam…'),
            game_closed: tr('steam_game_closed', 'Lance Elden Ring pour détecter les joueurs.'),
            waiting_log: tr('steam_waiting_log', 'En attente du journal Steam…'),
            steam_unavailable: tr('steam_unavailable', 'Steam est indisponible ou non connecté.'),
            helper_error: tr('steam_error', 'La connexion à Steam a échoué.'),
            disabled: tr('steam_off', 'Détection désactivée.'),
            active: tr('steam_empty', 'Aucun autre joueur détecté.')
        })[name] || tr('steam_error', 'La connexion à Steam a échoué.');
    }
    function render() {
        if (!state) return;
        const peers = Array.isArray(state.peers) ? state.peers : [];
        host.hidden = !state.world_host;
        if (state.world_host) {
            const hostName = typeof state.world_host.name === 'string' ? state.world_host.name.trim() : '';
            host.textContent = tr('steam_world_host', 'Hôte du monde (nom en jeu)') + ' : ' +
                (hostName || tr('steam_world_host_unknown', 'Non identifié'));
        }
        settingsStatus.textContent = state.status === 'active' ? tr('detection_enabled', 'Détection activée') : message(state.status);
        enabled.value = state.enabled ? 'true' : 'false';
        if (['active', 'steam_only', 'unavailable', 'denied'].includes(state.ping_mode)) pingPending = false;
        const pingMessages = {
            steam_only: tr('steam_ping_steam_only', 'Le ping Steam est affiché lorsqu’il est disponible.'),
            active: tr('steam_ping_active', 'Mesure avancée des pings active.'),
            unavailable: tr('steam_ping_unavailable', 'La mesure réseau Windows est indisponible.'),
            denied: tr('steam_ping_denied', 'Autorisation administrateur refusée ou mesure indisponible.'),
            requesting: tr('steam_ping_requesting', 'Confirme la demande administrateur Windows.'),
            admin_required: tr('steam_ping_required', 'Mesure avancée désactivée.')
        };
        const pingMode = storeBuild ? 'steam_only' : state.ping_mode;
        const pingMessage = pingPending ? pingMessages.requesting : (pingMessages[pingMode] || pingMessages.admin_required);
        const p2pReady = state.status === 'active' && ['active', 'steam_only'].includes(pingMode) && !pingPending;
        status.textContent = state.status !== 'active' ? message(state.status) :
            (peers.length === 0 ? message('active') : (p2pReady ? '' : pingMessage));
        status.classList.toggle('steam-empty', state.status === 'starting' || (state.status === 'active' && peers.length === 0));
        pingStatus.textContent = pingMessage;
        pingHelp.hidden = pingMode === 'steam_only';
        pingButton.hidden = pingMode === 'steam_only';
        pingButton.disabled = pingPending || pingMode === 'active' || pingMode === 'requesting';
        const current = new Set();
        let position = 0;
        peers.forEach(function(peer) {
            if (!peer || typeof peer.id !== 'string' || !/^\d{17}$/.test(peer.id)) return;
            current.add(peer.id);
            let item = cards.get(peer.id);
            if (!item) { item = createCard(peer.id); cards.set(peer.id, item); }
            renderCard(item, peer);
            const existing = list.children[position++];
            if (existing !== item) list.insertBefore(item, existing || null);
        });
        cards.forEach(function(item, id) {
            if (!current.has(id)) { item.remove(); cards.delete(id); }
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
    document.addEventListener('tracker-overlay-options-change', function (event) {
        if (!event.detail || typeof event.detail !== 'object') return;
        playerOptions = Object.assign({}, event.detail);
        render();
    });
    refresh(); setInterval(refresh, 3000);
})();
