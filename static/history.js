(function () {
    const panel = document.getElementById('history_panel');
    const button = document.getElementById('menu_button_history');
    const mode = document.getElementById('history_mode');
    const list = document.getElementById('history_list');
    const more = document.getElementById('history_more');
    const count = document.getElementById('history_count');
    // Move the existing controls when the running server still has the old template cached.
    const controls = panel.querySelector('.history-storage-controls');
    const archivesSection = panel.querySelector('.history-archives');
    if (controls && archivesSection) {
        let storageSection = panel.querySelector('.history-storage-section');
        if (!storageSection) {
            storageSection = document.createElement('section');
            storageSection.className = 'history-storage-section';
            archivesSection.before(storageSection);
        }
        [controls, document.getElementById('history_storage_note'), document.getElementById('history_monitor_note'), document.getElementById('history_action_status')].filter(Boolean).forEach(node => storageSection.appendChild(node));
    }
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
    let storage = null, mutationPending = false, storageRequest = 0;
    const storageSize = document.getElementById('history_storage_size');
    const storageNote = document.getElementById('history_storage_note');
    const purge = document.getElementById('history_purge');
    const archive = document.getElementById('history_archive');
    const archiveList = document.getElementById('history_archives_list');
    const actionStatus = document.getElementById('history_action_status');
    const monitorNote = document.getElementById('history_monitor_note');
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
    function formatSize(bytes) {
        if (!Number.isFinite(bytes) || bytes < 0) return '—';
        const units = ['B','KiB','MiB','GiB','TiB'];
        let index = 0;
        while (bytes >= 1024 && index < units.length - 1) { bytes /= 1024; index++; }
        return new Intl.NumberFormat(document.documentElement.lang || undefined, {maximumFractionDigits:1}).format(bytes) + ' ' + units[index];
    }
    function renderStorage() {
        if (!storage || !storageSize || !archiveList) return;
        storageSize.textContent = (storage.history.estimated ? tr('history_estimated', 'Environ') + ' ' : '') + formatSize(storage.history.bytes);
        if (storageNote) {
            storageNote.dataset.i18n = storage.history.estimated ? 'history_storage_estimated_note' : 'history_storage_note';
            storageNote.dataset.i18nFr = storage.history.estimated
                ? 'Estimation de la taille des données de l’historique actif dans la base locale.'
                : 'Espace alloué dans la base locale : après une purge, SQLite peut le réutiliser sans réduire immédiatement la taille du fichier.';
            storageNote.textContent = tr(storageNote.dataset.i18n, storageNote.dataset.i18nFr);
        }
        const stopped = !storage.monitor_running;
        purge.disabled = archive.disabled = mutationPending || !stopped || storage.history.events === 0;
        monitorNote.textContent = stopped ? '' : tr('history_stop_required', 'Arrête le suivi pour archiver ou purger l’historique.');
        archiveList.replaceChildren();
        if (!storage.archives.length) {
            archiveList.appendChild(element('p', 'history-archives-empty', tr('history_archives_empty', 'Aucune archive pour le moment.')));
            return;
        }
        storage.archives.forEach(function(item) {
            const row = element('div', 'history-archive-row tracker-frame');
            const details = element('div', 'history-archive-details');
            const date = element('time', '', formatDate(item.created_at));
            date.dateTime = item.created_at.replace(' ', 'T');
            const summary = element('span', '', new Intl.NumberFormat(document.documentElement.lang || undefined).format(item.events) + ' ' + tr('history_archive_events', 'événements') + ' · ' + tr('history_archive_data', 'données chiffrées') + ' : ' + formatSize(item.bytes));
            const restore = element('button', '', tr('history_restore', 'Restaurer'));
            restore.type = 'button'; restore.disabled = mutationPending;
            restore.setAttribute('aria-label', tr('history_restore', 'Restaurer') + ' : ' + formatDate(item.created_at));
            restore.addEventListener('click', () => mutate('/history-archives/' + item.id + '/restore', 'restore'));
            details.append(date, summary); row.append(details, restore); archiveList.appendChild(row);
        });
    }
    async function refreshStorage() {
        if (!storageSize) return;
        const version = ++storageRequest;
        try {
            const response = await fetch('/history-storage', {cache:'no-store'});
            if (!response.ok) throw new Error('storage');
            const result = await response.json();
            if (result.request !== 'success') throw new Error('storage');
            if (version !== storageRequest) return;
            storage = result; renderStorage();
        } catch (_) {
            if (version !== storageRequest) return;
            storage = null; storageSize.textContent = '—'; purge.disabled = archive.disabled = true;
            monitorNote.textContent = tr('history_storage_error', 'Impossible de charger les informations de l’historique.');
        }
    }
    async function mutate(url, kind) {
        if (mutationPending) return;
        const confirmation = kind === 'purge'
            ? tr('history_purge_confirm', 'Supprimer définitivement tout l’historique actif, y compris les rencontres Steam ? Les archives, captures et statistiques sont conservées.')
            : kind === 'archive'
                ? tr('history_archive_confirm', 'Archiver tout l’historique actif et le retirer de cette liste ? Les rencontres Steam seront aussi archivées. Les captures et statistiques sont conservées.')
                : tr('history_restore_confirm', 'Restaurer les événements absents de cette archive dans l’historique actif ? L’archive sera conservée.');
        if (!window.confirm(confirmation)) return;
        mutationPending = true; renderStorage(); actionStatus.textContent = '';
        try {
            const response = await fetch(url, {method:'POST'});
            const result = await response.json();
            if (!response.ok || result.request !== 'success') {
                if (result.reason === 'monitor_running') throw new Error('monitor_running');
                if (result.reason === 'empty') throw new Error('empty');
                throw new Error('request');
            }
            actionStatus.textContent = kind === 'purge' ? tr('history_purge_done', 'Historique actif purgé.') :
                kind === 'archive' ? tr('history_archive_done', 'Historique archivé et retiré de la liste active.') :
                result.restored ? tr('history_restore_done', 'Les événements absents ont été restaurés.') : tr('history_restore_none', 'Tous les événements de cette archive sont déjà présents.');
            generation++; entries = []; hasMore = false; render();
            load('initial');
        } catch (error) {
            actionStatus.textContent = error.message === 'monitor_running' ? tr('history_stop_required', 'Arrête le suivi pour archiver ou purger l’historique.') :
                error.message === 'empty' ? tr('history_archive_empty_error', 'Il n’y a aucun événement à archiver.') : tr('history_action_error', 'L’opération a échoué. Réessaie.');
        } finally { mutationPending = false; await refreshStorage(); }
    }
    if (purge && archive) {
        purge.addEventListener('click', () => mutate('/history-purge', 'purge'));
        archive.addEventListener('click', () => mutate('/history-archives', 'archive'));
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
                }
            }
            text = text.replace(/Time:/g, tr('time', 'Temps') + ':');
            text.split('\n').forEach(function(line, i) {
                if (i) message.appendChild(document.createElement('br'));
                const translatedWarnings = Object.values(window.ELDEN_UI_PACKS || {}).map(pack => pack.modern.inventory_warning);
                message.appendChild(element('span', line.startsWith('Pensez à retirer') || translatedWarnings.includes(line) ? 'history-warning' : '', line));
            });
            if (entry.kind === 'steam_encounter' && entry.metadata && entry.metadata.country_code) {
                const country = element('div', 'history-steam-country');
                window.appendIpCountry(country, entry.metadata.country_code);
                message.appendChild(country);
            }
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
        refreshStorage();
        poller = setInterval(() => { load('refresh'); refreshStorage(); }, 5000);
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
    document.addEventListener('ui-language-change', function() { if (!panel.hidden) { render(); renderStorage(); } });
    more.addEventListener('click', () => load('older'));
})();
