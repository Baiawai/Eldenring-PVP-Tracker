(function () {
    const panel = document.getElementById('history_panel');
    const button = document.getElementById('menu_button_history');
    const mode = document.getElementById('history_mode');
    const list = document.getElementById('history_list');
    const more = document.getElementById('history_more');
    const count = document.getElementById('history_count');
    // Move existing controls out of a server-cached older history template.
    const dataSection = document.querySelector('.contente_settings[setting="9"]');
    const settingsPanel = document.querySelector('.settings-panel');
    const controls = document.querySelector('.history-storage-controls');
    const archivesSection = document.querySelector('.history-archives');
    if (dataSection && controls && archivesSection) {
        let storageSection = controls.closest('.history-storage-section');
        if (!storageSection) {
            storageSection = document.createElement('section');
            storageSection.className = 'history-storage-section';
            archivesSection.before(storageSection);
        }
        [controls, document.getElementById('history_storage_note'), document.getElementById('history_monitor_note'), document.getElementById('history_action_status')].filter(Boolean).forEach(node => storageSection.appendChild(node));
        let group = dataSection.querySelector('.history-data-settings');
        if (!group) {
            group = document.createElement('div');
            group.className = 'history-data-settings';
            const heading = document.createElement('h2');
            heading.id = 'history_data_title';
            heading.dataset.i18n = 'history_data_title';
            heading.dataset.i18nFr = 'Données de l’historique';
            heading.textContent = window.uiT ? window.uiT('history_data_title', heading.dataset.i18nFr) : heading.dataset.i18nFr;
            group.setAttribute('aria-labelledby', heading.id);
            group.appendChild(heading);
            dataSection.appendChild(group);
        }
        group.append(storageSection, archivesSection);
        const intro = archivesSection.querySelector('[data-i18n="history_archives_intro"]');
        if (intro) {
            intro.dataset.i18nFr = 'Archive l’historique actif pour le retirer de la liste de l’historique. Les archives restent stockées localement et peuvent être restaurées.';
            intro.textContent = window.uiT ? window.uiT('history_archives_intro', intro.dataset.i18nFr) : intro.dataset.i18nFr;
        }
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
    let autoLoadBlocked = false;
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
    // Keep the journal scrollable without pushing the archive controls away.
    list.tabIndex = 0;
    const moreError = element('p', 'history-action-status');
    moreError.hidden = true;
    moreError.setAttribute('role', 'status');
    more.before(moreError);

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
    function historicalOpponent(line) {
        const templates = ['Vous remportez la victoire contre {opponent} !', 'Vous avez perdu contre {opponent}.', 'Le combat s’achève par une égalité avec {opponent}.'];
        Object.values(window.ELDEN_UI_PACKS || {}).forEach(function(pack) {
            if (pack.modern) templates.push(pack.modern.victory_against, pack.modern.defeat_against, pack.modern.draw_against);
        });
        for (const template of templates) {
            if (typeof template !== 'string' || !template.includes('{opponent}')) continue;
            const parts = template.split('{opponent}');
            if (parts.length !== 2 || !line.startsWith(parts[0]) || !line.endsWith(parts[1])) continue;
            const name = line.slice(parts[0].length, parts[1] ? -parts[1].length : undefined);
            if (name) return name;
        }
        return '';
    }
    // History stores the text as observed at the time. Translate only known
    // tracker templates; never guess at an arbitrary player name or OCR text.
    let recordedRolePrefixes = null;
    function localizedHistoryLine(line, metadata) {
        const frenchBackend = {4:'En attente de joueur(s)', 8:'Tous les combattants sont rassemblés',
            9:'Début du combat', 10:'Vous remportez la victoire !', 12:'Vous avez perdu',
            20:'Le combat s\'achève par une égalité'};
        const packs = Object.values(window.ELDEN_UI_PACKS || {});
        for (const [index, french] of Object.entries(frenchBackend)) {
            const candidates = [french, ...packs.map(pack => pack.backend && pack.backend[Number(index)])];
            if (candidates.some(value => typeof value === 'string' && !/<br\s*\/?\s*>/i.test(value) && value.trim() === line.trim())) {
                const language = window.uiCurrentLanguage ? window.uiCurrentLanguage() : 'fra';
                const target = window.ELDEN_UI_PACKS?.[language]?.backend?.[Number(index)] || french;
                return target.replace(/<br\s*\/?\s*>/gi, ' ').trim();
            }
        }
        const templates = [
            ['victory_against', 'Vous remportez la victoire contre {opponent} !', 'opponent'],
            ['defeat_against', 'Vous avez perdu contre {opponent}.', 'opponent'],
            ['draw_against', 'Le combat s’achève par une égalité avec {opponent}.', 'opponent'],
            ['tracking_defending_against', '{name} a envahi votre monde', 'name'],
            ['hunter_objective_completed_message', "Son objectif accompli, le Chasseur {name} s'en est retourné dans son monde.", 'name']
        ];
        for (const [key, french, placeholder] of templates) {
            const marker = '{' + placeholder + '}';
            const candidates = [french, ...packs.map(pack => pack.modern && pack.modern[key])];
            for (const template of candidates) {
                if (typeof template !== 'string' || !template.includes(marker)) continue;
                const pieces = template.split(marker);
                if (pieces.length !== 2 || !line.startsWith(pieces[0]) || !line.endsWith(pieces[1])) continue;
                const name = line.slice(pieces[0].length, pieces[1] ? -pieces[1].length : undefined);
                if (!name || (placeholder === 'opponent' && metadata.opponent && metadata.opponent !== name)) continue;
                return tr(key, french).replace(marker, () => name);
            }
        }
        const roles = [
            ['summoned_ally','Allié arrivé'], ['ally_left','Allié reparti'], ['ally_dismissed','Allié renvoyé dans son monde'], ['ally_died','Allié mort'],
            ['cooperator_summoned','Allié adverse arrivé'], ['cooperator_left','Allié adverse reparti'], ['cooperator_dismissed','Allié adverse renvoyé dans son monde'], ['cooperator_died','Allié adverse mort'],
            ['hunter_arrived','Chasseur arrivé'], ['hunter_summoning','Chasseur en cours d’invocation'], ['hunter_left','Chasseur reparti'],
            ['hunter_objective_completed','Objectif du chasseur accompli'], ['hunter_dismissed','Chasseur renvoyé dans son monde'], ['hunter_died','Chasseur mort'],
            ['coinvader_arrived','Autre envahisseur arrivé'], ['coinvader_died','Autre envahisseur mort'],
            ['invasion_detected','Envahisseur arrivé'], ['invader_died','Envahisseur mort']
        ];
        if (!recordedRolePrefixes) {
            recordedRolePrefixes = roles.flatMap(([key, french]) => [french, ...packs.map(pack => pack.modern && pack.modern[key])]
                .filter(value => typeof value === 'string' && value).map(value => ({value, key, french})));
            [['cooperator_summoned','arrivé'], ['cooperator_left','reparti'],
             ['cooperator_dismissed','renvoyé dans son monde'], ['cooperator_died','mort']].forEach(([key, suffix]) => {
                const french = roles.find(role => role[0] === key)[1];
                recordedRolePrefixes.push({value:'Coopérateur adverse ' + suffix, key, french});
            });
            recordedRolePrefixes.sort((a, b) => b.value.length - a.value.length);
        }
        for (const prefix of recordedRolePrefixes) {
            const marker = prefix.value + ' : ';
            if (line.startsWith(marker) && line.length > marker.length)
                return tr(prefix.key, prefix.french) + ' : ' + line.slice(marker.length);
        }
        return line;
    }
    function appendPlayerName(container, line, name, source, id) {
        const index = name ? line.indexOf(name) : -1;
        if (index < 0 || !window.openEncounteredPlayer) {
            container.appendChild(document.createTextNode(line));
            return;
        }
        const link = element('button', 'encounter-player-link', name);
        link.type = 'button';
        link.addEventListener('click', () => window.openEncounteredPlayer(name, source, id));
        container.append(document.createTextNode(line.slice(0, index)), link, document.createTextNode(line.slice(index + name.length)));
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
        if (stopped) window.uiSetStatus(monitorNote);
        else window.uiSetStatus(monitorNote, 'history_stop_required', 'Arrête le suivi pour archiver ou purger l’historique.');
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
            restore.type = 'button'; restore.disabled = mutationPending || !stopped;
            restore.setAttribute('aria-label', tr('history_restore', 'Restaurer') + ' : ' + formatDate(item.created_at));
            restore.addEventListener('click', () => mutate('/history-archives/' + item.id + '/restore', 'restore'));
            const remove = element('button', '', tr('history_archive_delete', 'Supprimer'));
            remove.type = 'button'; remove.disabled = mutationPending || !stopped;
            remove.setAttribute('aria-label', tr('history_archive_delete', 'Supprimer') + ' : ' + formatDate(item.created_at));
            remove.addEventListener('click', () => mutate('/history-archives/' + item.id + '/delete', 'delete'));
            const actions = element('div', 'history-archive-actions');
            actions.append(restore, remove);
            details.append(date, summary); row.append(details, actions); archiveList.appendChild(row);
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
            window.uiSetStatus(monitorNote, 'history_storage_error', 'Impossible de charger les informations de l’historique.');
        }
    }
    async function mutate(url, kind) {
        if (mutationPending) return;
        const confirmation = kind === 'purge'
            ? tr('history_purge_confirm', 'Supprimer définitivement tout l’historique actif, y compris les rencontres Steam ? Les archives, captures et statistiques sont conservées.')
            : kind === 'archive'
                ? tr('history_archive_confirm', 'Archiver tout l’historique actif et le retirer de la liste de l’historique ? Les rencontres Steam seront aussi archivées. Les captures et statistiques sont conservées.')
                : kind === 'delete'
                    ? tr('history_archive_delete_confirm', 'Supprimer définitivement cette archive ? L’historique actif, les captures et les statistiques sont conservés.')
                    : tr('history_restore_confirm', 'Restaurer les événements absents de cette archive dans l’historique actif ? L’archive sera conservée.');
        if (!window.confirm(confirmation)) return;
        mutationPending = true; renderStorage(); window.uiSetStatus(actionStatus);
        try {
            const response = await fetch(url, {method:'POST'});
            const result = await response.json();
            if (!response.ok || result.request !== 'success') {
                if (result.reason === 'monitor_running') throw new Error('monitor_running');
                if (result.reason === 'empty') throw new Error('empty');
                throw new Error('request');
            }
            if (kind === 'purge') window.uiSetStatus(actionStatus, 'history_purge_done', 'Historique actif purgé.');
            else if (kind === 'archive') window.uiSetStatus(actionStatus, 'history_archive_done', 'Historique archivé et retiré de la liste active.');
            else if (kind === 'restore' && result.restored) window.uiSetStatus(actionStatus, 'history_restore_done', 'Les événements absents ont été restaurés.');
            else if (kind === 'restore') window.uiSetStatus(actionStatus, 'history_restore_none', 'Tous les événements de cette archive sont déjà présents.');
            if (kind !== 'delete') {
                generation++; entries = []; hasMore = false; autoLoadBlocked = false; render();
                load('initial');
            }
        } catch (error) {
            if (error.message === 'monitor_running') window.uiSetStatus(actionStatus, 'history_stop_required', 'Arrête le suivi pour archiver ou purger l’historique.');
            else if (error.message === 'empty') window.uiSetStatus(actionStatus, 'history_archive_empty_error', 'Il n’y a aucun événement à archiver.');
            else window.uiSetStatus(actionStatus, 'history_action_error', 'L’opération a échoué. Réessaie.');
        } finally { mutationPending = false; await refreshStorage(); }
    }
    if (purge && archive) {
        purge.addEventListener('click', () => mutate('/history-purge', 'purge'));
        archive.addEventListener('click', () => mutate('/history-archives', 'archive'));
    }
    // Storage controls now live in settings, independently of the journal page.
    let storagePoller = null;
    function updateStorageVisibility() {
        const visible = dataSection && settingsPanel && dataSection.getClientRects().length > 0;
        if (visible && !storagePoller) {
            if (purge && archive) purge.disabled = archive.disabled = true;
            if (archiveList) archiveList.querySelectorAll('button').forEach(button => { button.disabled = true; });
            refreshStorage();
            storagePoller = setInterval(refreshStorage, 5000);
        } else if (!visible && storagePoller) {
            clearInterval(storagePoller); storagePoller = null;
            storageRequest++;
        }
    }
    if (dataSection && settingsPanel) {
        const observer = new MutationObserver(updateStorageVisibility);
        observer.observe(dataSection, {attributes:true, attributeFilter:['class','style','hidden']});
        observer.observe(settingsPanel, {attributes:true, attributeFilter:['class','style','hidden']});
        updateStorageVisibility();
    }
    function render(preservePosition) {
        const anchor = preservePosition && Array.from(list.querySelectorAll('.history-entry')).find(card => card.getBoundingClientRect().bottom > list.getBoundingClientRect().top);
        const anchorId = anchor && anchor.dataset.historyId;
        const anchorOffset = anchor && anchor.getBoundingClientRect().top;
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
            card.dataset.historyId = entry.id;
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
                const metadata = entry.metadata || {};
                if (entry.kind === 'detection') line = localizedHistoryLine(line, metadata);
                if (i) message.appendChild(document.createElement('br'));
                const translatedWarnings = Object.values(window.ELDEN_UI_PACKS || {}).map(pack => pack.modern.inventory_warning);
                const span = element('span', line.startsWith('Pensez à retirer') || translatedWarnings.includes(line) ? 'history-warning' : '');
                const steamEvent = entry.kind && entry.kind.startsWith('steam_');
                const name = i === 0 ? (steamEvent ? (metadata.name || metadata.id || '') : (metadata.opponent || historicalOpponent(line))) : '';
                appendPlayerName(span, line, name, steamEvent ? 'steam' : (metadata.opponent_source || ''), steamEvent ? String(metadata.id || '') : '');
                message.appendChild(span);
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
        if (anchorId) {
            const replacement = Array.from(list.querySelectorAll('.history-entry')).find(card => card.dataset.historyId === anchorId);
            if (replacement) list.scrollTop += replacement.getBoundingClientRect().top - anchorOffset;
        }
    }
    function maybeLoadOlder() {
        if (panel.hidden || loading || !hasMore || autoLoadBlocked) return;
        if (list.scrollHeight - list.clientHeight - list.scrollTop <= 160) load('older');
    }
    async function load(kind) {
        if (loading || panel.hidden) return;
        if (kind !== 'refresh') moreError.hidden = true;
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
                const refreshed = data.events.slice();
                let cursorPage = data;
                // A busy interval may add more than one page. Fill the gap to
                // the old head before merging, still requesting only 30 at a time.
                while (entries.length && cursorPage.has_more && cursorPage.events.length &&
                       !cursorPage.events.some(entry => known.has(entry.id)) &&
                       cursorPage.events[cursorPage.events.length - 1].id > entries[0].id) {
                    query.set('before', String(cursorPage.events[cursorPage.events.length - 1].id));
                    const olderResponse = await fetch('/detection-history?' + query.toString(), {cache:'no-store'});
                    if (!olderResponse.ok) throw new Error('history request failed');
                    cursorPage = await olderResponse.json();
                    if (version !== generation || panel.hidden) return;
                    refreshed.push(...cursorPage.events);
                }
                const fresh = new Map(refreshed.map(entry => [entry.id, entry]));
                const added = refreshed.filter(entry => !known.has(entry.id));
                if (!added.length && entries.every(entry => !fresh.has(entry.id) || JSON.stringify(entry) === JSON.stringify(fresh.get(entry.id)))) return;
                entries = added.concat(entries.map(entry => fresh.get(entry.id) || entry));
                if (!entries.length || entries.length <= data.events.length) hasMore = data.has_more;
            } else {
                entries = data.events;
                hasMore = data.has_more;
            }
            render(kind === 'older' || (kind === 'refresh' && list.scrollTop > 0));
        } catch (error) {
            if (version === generation && !panel.hidden && kind !== 'refresh') {
                if (kind === 'older') {
                    autoLoadBlocked = true;
                    moreError.textContent = tr('history_error', 'Impossible de charger l’historique. Réessaie dans un instant.');
                    moreError.hidden = false;
                }
                else list.replaceChildren(element('div', 'history-empty tracker-frame', tr('history_error', 'Impossible de charger l’historique. Réessaie dans un instant.')));
            }
        } finally {
            loading = false;
            more.disabled = false;
            if (version !== generation && !panel.hidden) load('initial');
            else if (!panel.hidden && kind !== 'refresh') requestAnimationFrame(maybeLoadOlder);
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
        autoLoadBlocked = false;
        list.scrollTop = 0;
        generation++;
        load('initial');
        poller = setInterval(() => { load('refresh'); }, 5000);
    });
    ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_players', 'menu_button_info', 'start'].forEach(function(id) {
        document.getElementById(id).addEventListener('click', closeHistory);
    });
    mode.addEventListener('change', function() {
        generation++;
        entries = [];
        hasMore = false;
        autoLoadBlocked = false;
        list.scrollTop = 0;
        render();
        load('initial');
    });
    document.addEventListener('ui-language-change', function() {
        if (dataSection && dataSection.getClientRects().length) renderStorage();
        if (!panel.hidden) {
            render(true); renderStorage();
            if (!moreError.hidden) moreError.textContent = tr('history_error', 'Impossible de charger l’historique. Réessaie dans un instant.');
        }
    });
    list.addEventListener('scroll', maybeLoadOlder, {passive:true});
    more.addEventListener('click', () => { autoLoadBlocked = false; load('older'); });
})();
