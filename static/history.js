(function () {
    const panel = document.getElementById('history_panel');
    const button = document.getElementById('menu_button_history');
    const mode = document.getElementById('history_mode');
    const list = document.getElementById('history_list');
    const more = document.getElementById('history_more');
    const count = document.getElementById('history_count');
    // Support an older template cached by the running server.
    const modeLabelNode = document.querySelector('label[for="history_mode"]');
    modeLabelNode.dataset.i18n = 'history_category';
    modeLabelNode.dataset.i18nFr = 'Catégorie';
    const allOption = mode.querySelector('option[value="all"]');
    allOption.dataset.i18n = 'history_all_categories';
    allOption.dataset.i18nFr = 'Toutes les catégories';
    if (!mode.querySelector('option[value="System"]')) {
        const option = new Option('Système', 'System');
        option.dataset.i18n = 'history_system';
        allOption.after(option);
    }
    let entries = [];
    let hasMore = false;
    let generation = 0;
    let loading = false;
    let poller = null;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;

    function element(tag, cls, value) {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (value !== undefined) node.textContent = value;
        return node;
    }
    function formatDate(value) {
        const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(value || '');
        return match ? match[3] + '/' + match[2] + '/' + match[1] + ' · ' + match[4] + ':' + match[5] : value;
    }
    function modeLabel(value) {
        return ({Arena:tr('arena','Arène 1v1'), Invasion:tr('invasion','Invasions'), Defense:tr('defense','Monde envahi'), System:tr('history_system','Système'), Unknown:tr('unknown_mode','Mode non déterminé')})[value] || tr('unknown_mode','Mode non déterminé');
    }
    function render() {
        list.replaceChildren();
        count.textContent = window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('events_shown', 'Événements affichés') + ' : ' + entries.length : entries.length + (entries.length === 1 ? ' événement affiché' : ' événements affichés');
        more.hidden = !hasMore;
        if (!entries.length) {
            list.appendChild(element('div', 'history-empty tracker-frame', tr('history_category_empty', 'Aucun événement enregistré pour cette catégorie.')));
            return;
        }
        const fragment = document.createDocumentFragment();
        entries.forEach(function(entry) {
            const card = element('article', 'history-entry tracker-frame');
            const time = element('time', '', formatDate(entry.date));
            time.dateTime = entry.date.replace(' ', 'T');
            const message = element('div', 'history-message');
            let text = entry.message;
            if (!window.uiCurrentLanguage || window.uiCurrentLanguage() === 'fra') text = text.replace(/^Coopérateur adverse(?= (?:arrivé|reparti|renvoyé|mort|observé))/,'Allié adverse');
            if (entry.kind === 'monitor_start') text = tr('monitor_started', 'Suivi démarré');
            if (entry.kind === 'monitor_stop') text = tr('history_monitor_stopped', 'Suivi arrêté');
            if (entry.kind === 'monitor_error') text = tr('history_monitor_error', 'Suivi arrêté à cause d’une erreur');
            if (entry.metadata && entry.kind && entry.kind.startsWith('steam_')) {
                const label = entry.kind === 'steam_encounter' ? tr('steam_history_encounter', 'Joueur Steam rencontré') : null;
                if (label) {
                    text = label + ' : ' + (entry.metadata.name || entry.metadata.id);
                    if (entry.mode === 'Arena' && entry.metadata.outcome) {
                        const outcome = ({victory:tr('victory','Victoire'), defeat:tr('defeat','Défaite'), draw:tr('draw','Égalité')})[entry.metadata.outcome];
                        if (outcome) text += ' · ' + outcome;
                    }
                    if (entry.metadata.ip) text += '\n' + (entry.metadata.relay ? tr('steam_ip_relay','Relais') : tr('steam_ip_label','IP réseau')) + ' : ' + entry.metadata.ip;
                }
            }
            text = text.replace(/Time:/g, tr('time', 'Temps') + ':');
            text.split('\n').forEach(function(line, i) {
                if (i) message.appendChild(document.createElement('br'));
                const translatedWarnings = Object.values(window.ELDEN_UI_PACKS || {}).map(pack => pack.modern.inventory_warning);
                message.appendChild(element('span', line.startsWith('Pensez à retirer') || translatedWarnings.includes(line) ? 'history-warning' : '', line));
            });
            card.append(time, message, element('span', 'history-mode', modeLabel(entry.mode)));
            fragment.appendChild(card);
        });
        list.appendChild(fragment);
    }
    async function load(kind) {
        if (loading || panel.hidden) return;
        const version = generation;
        const filter = mode.value;
        const before = kind === 'older' && entries.length ? entries[entries.length - 1].id : 0;
        loading = true;
        more.disabled = true;
        try {
            const query = new URLSearchParams({mode:filter});
            if (before) query.set('before', String(before));
            const response = await fetch('/detection-history?' + query.toString(), {cache:'no-store'});
            if (!response.ok) throw new Error('history request failed');
            const data = await response.json();
            if (version !== generation || panel.hidden) return;
            if (kind === 'older') {
                entries = entries.concat(data.events);
                hasMore = data.has_more;
            } else if (kind === 'refresh') {
                const known = new Set(entries.map(entry => entry.id));
                const fresh = new Map(data.events.map(entry => [entry.id, entry]));
                entries = data.events.filter(entry => !known.has(entry.id)).concat(entries.map(entry => fresh.get(entry.id) || entry));
                if (!entries.length || entries.length <= data.events.length) hasMore = data.has_more;
            } else {
                entries = data.events;
                hasMore = data.has_more;
            }
            render();
        } catch (error) {
            if (version === generation && !panel.hidden && kind !== 'refresh') {
                list.replaceChildren(element('div', 'history-empty tracker-frame', tr('history_error', 'Impossible de charger l’historique. Réessaie dans un instant.')));
            }
        } finally {
            loading = false;
            more.disabled = false;
            if (version !== generation && !panel.hidden) load('initial');
        }
    }
    function closeHistory() {
        panel.hidden = true;
        button.classList.remove('active');
        generation++;
        if (poller) clearInterval(poller);
        poller = null;
    }
    button.addEventListener('click', function() {
        if (!panel.hidden) { closeHistory(); return; }
        ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_players'].forEach(function(id) {
            const other = document.getElementById(id);
            if (other.classList.contains('active')) other.click();
        });
        panel.hidden = false;
        button.classList.add('active');
        entries = [];
        hasMore = false;
        generation++;
        load('initial');
        poller = setInterval(() => load('refresh'), 5000);
    });
    ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_players', 'menu_button_info', 'start'].forEach(function(id) {
        document.getElementById(id).addEventListener('click', closeHistory);
    });
    mode.addEventListener('change', function() {
        generation++;
        entries = [];
        hasMore = false;
        render();
        load('initial');
    });
    document.addEventListener('ui-language-change', function() { if (!panel.hidden) render(); });
    more.addEventListener('click', () => load('older'));
})();
