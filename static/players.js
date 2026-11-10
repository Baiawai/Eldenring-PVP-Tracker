(function () {
    const panel = document.getElementById('players_panel');
    const menuButton = document.getElementById('menu_button_players');
    const search = document.getElementById('players_search');
    const sort = document.getElementById('players_sort');
    const list = document.getElementById('players_list');
    let players = [];
    let activeFilter = 'all';
    let lastRequest = 0;
    let lastRevision = null;
    let unnamedCaptures = 0;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function normalize(value) {
        return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
    }

    function formatDate(value) {
        const match = /^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?/.exec(value || '');
        if (!match) return value || tr('date_unknown', 'Date inconnue');
        return match[3] + '/' + match[2] + '/' + match[1] + (match[4] ? ' · ' + match[4] + ':' + match[5] : '');
    }

    function modeLabel(mode) {
        return ({Arena: tr('arena', 'Arène 1v1'), Invasion: tr('invasion', 'Invasions'), Defense: tr('defense', 'Monde envahi')})[mode] || tr('unknown_mode', 'Mode non déterminé');
    }

    function outcomeLabel(outcome) {
        return ({victory: tr('victory', 'Victoire'), defeat: tr('defeat', 'Défaite'), draw: tr('draw', 'Égalité')})[outcome] || tr('no_result', 'Sans résultat');
    }

    function sightingLabel(player) {
        if (player.steam) return tr('steam_profile', 'Profil Steam');
        if (player.roles.includes('hunter')) {
            if (player.relations.includes('ally') && player.relations.includes('opponent')) return tr('hunter_mixed', 'Chasseur · camps multiples');
            if (player.relations.includes('opponent')) return tr('hunter_opponent', 'Chasseur adverse');
            if (player.relations.includes('ally')) return tr('hunter_ally', 'Chasseur allié');
            return tr('hunter_unknown', 'Chasseur · camp non déterminé');
        }
        if (player.roles.includes('invader')) return player.relations.includes('coinvader') ? tr('co_invader', 'Autre envahisseur') : tr('invader', 'Envahisseur');
        if (player.roles.includes('cooperator')) return tr('enemy_cooperator', 'Allié adverse');
        if (player.roles.includes('ally')) return tr('summoned_ally', 'Allié invoqué');
        return tr('encounter_observed', 'Rencontre observée');
    }

    function playerCard(player) {
        const card = element('details', 'player-card tracker-frame');
        const summary = element('summary');
        const initials = Array.from(player.name.trim())[0] || '?';
        summary.appendChild(element('span', 'player-emblem', initials.toLocaleUpperCase()));
        const identity = element('span', 'player-identity');
        const profileStatus = element('p', 'player-profile-status');
        profileStatus.setAttribute('role', 'status');
        const steamId = player.steam && /^[0-9]{17}$/.test(player.steam.id) ? player.steam.id : null;
        if (steamId) {
            const nameButton = element('button', 'player-name player-profile-button', player.name);
            nameButton.type = 'button';
            nameButton.title = tr('steam_profile_open', 'Ouvrir le profil dans Steam');
            nameButton.addEventListener('click', async function(event) {
                event.preventDefault();
                event.stopPropagation();
                card.open = true;
                profileStatus.textContent = '';
                try {
                    const response = await fetch('/steam-profile', {method:'POST', body:new URLSearchParams({steam_id:steamId})});
                    if (!response.ok) throw new Error('request');
                    profileStatus.textContent = tr('steam_profile_sent', 'Profil demandé : reviens dans le jeu pour voir Steam.');
                } catch (_) {
                    profileStatus.textContent = tr('steam_profile_error', 'Impossible d’ouvrir ce profil dans Steam.') + ' ' + tr('steam_profile_browser_hint', 'Tu peux utiliser le lien ci-dessous.');
                }
            });
            identity.appendChild(nameButton);
        } else {
            identity.appendChild(element('strong', 'player-name', player.name));
        }
        const roles = element('span', 'player-roles');
        if (player.steam) roles.appendChild(element('span', 'player-role', tr('steam_profile', 'Profil Steam')));
        if (player.relations.includes('opponent')) roles.appendChild(element('span', 'player-role', tr('opponent', 'Adversaire')));
        if (player.relations.includes('ally')) roles.appendChild(element('span', 'player-role', tr('ally', 'Allié')));
        if (player.relations.includes('coinvader')) roles.appendChild(element('span', 'player-role', tr('co_invader', 'Autre envahisseur'))); 
        if (player.roles.includes('hunter')) roles.appendChild(element('span', 'player-role', tr('hunter', 'Chasseur')));
        if (player.relations.includes('unknown')) roles.appendChild(element('span', 'player-role', tr('unknown_side', 'Camp non déterminé')));
        identity.appendChild(roles);
        const activity = [];
        if (player.total) activity.push((window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('fights', 'Combats') + ' : ' + player.total : player.total + (player.total === 1 ? ' combat' : ' combats')));
        if (player.steam && ['Invasion', 'Defense'].includes(player.steam.mode)) activity.push(tr('steam_profile_unlinked', 'Personnage non confirmé'));
        if (player.sightings) activity.push((window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('sightings', 'Observations') + ' : ' + player.sightings : player.sightings + (player.sightings === 1 ? ' apparition observée' : ' apparitions observées')));
        identity.appendChild(element('span', 'player-meta', activity.join(' · ') + ' · ' + tr('last_seen', 'Dernier') + ' : ' + formatDate(player.last_seen)));
        summary.appendChild(identity);
        const record = element('span', 'player-record');
        if (player.total) {
            record.appendChild(element('span', 'win', player.victories + ' V'));
            record.appendChild(element('span', 'loss', player.defeats + ' D'));
            if (player.draws > 0 || player.history.some(match => match.mode === 'Arena')) record.appendChild(element('span', 'draw', player.draws + ' E'));
        } else {
            record.appendChild(element('span', 'none', sightingLabel(player)));
        }
        summary.appendChild(record);
        summary.appendChild(element('span', 'player-expand', '⌄'));
        card.appendChild(summary);
        const history = element('div', 'player-history');
        if (steamId) {
            history.appendChild(profileStatus);
            const browserLink = element('a', 'player-profile-web', tr('steam_profile_browser', 'Ouvrir le profil dans le navigateur'));
            browserLink.href = 'https://steamcommunity.com/profiles/' + steamId;
            browserLink.target = '_blank';
            browserLink.rel = 'noopener noreferrer';
            history.appendChild(browserLink);
        }
        if (player.steam && player.steam.country_code) {
            const country = element('div', 'player-steam-country');
            window.appendIpCountry(country, player.steam.country_code);
            history.appendChild(country);
        }
        history.appendChild(element('h3', '', player.total + player.sightings > 20 ? tr('recent_twenty', '20 dernières activités') : tr('recent_activity', 'Historique des rencontres')));
        player.history.forEach(function(match) {
            const line = element('div', 'player-match');
            let label = outcomeLabel(match.outcome);
            if (match.kind === 'steam') {
                label = match.outcome ? outcomeLabel(match.outcome) : tr('steam_history_encounter', 'Joueur Steam rencontré');
            }
            if (match.kind === 'sighting') {
                if (match.role === 'invader') label = match.relation === 'coinvader' ?
                    (match.event === 'died' ? tr('coinvader_died', 'Autre envahisseur mort') : tr('coinvader_arrived', 'Autre envahisseur arrivé')) :
                    (match.event === 'died' ? tr('invader_died', 'Envahisseur mort') : tr('invasion_detected', 'Invasion détectée'));
                else if (match.role === 'hunter') label = ({summoning: tr('hunter_summoning', 'Invocation de chasseur observée'), joined: tr('hunter_arrived', 'Chasseur arrivé'), left: tr('hunter_left', 'Chasseur reparti'), dismissed: tr('hunter_dismissed', 'Chasseur renvoyé'), died: tr('hunter_died', 'Chasseur mort')})[match.event] || tr('hunter_observed', 'Chasseur observé');
                else if (match.event === 'died') label = match.role === 'cooperator' ? tr('cooperator_died', 'Allié adverse mort') : tr('ally_died', 'Allié mort');
                else if (match.event === 'dismissed') label = match.role === 'cooperator' ? tr('cooperator_dismissed', 'Allié adverse renvoyé dans son monde') : tr('ally_dismissed', 'Allié renvoyé dans son monde');
                else if (match.event === 'left') label = match.role === 'cooperator' ? tr('cooperator_left', 'Allié adverse reparti') : tr('ally_left', 'Allié reparti');
                else label = match.role === 'cooperator' ? tr('cooperator_summoned', 'Allié adverse arrivé') : tr('summoned_ally', 'Allié invoqué');
                if (match.relation === 'opponent') label += ' · ' + tr('enemy_side', 'Camp adverse');
                if (match.relation === 'unknown') label += ' · ' + tr('unknown_side', 'Camp non déterminé');
            }
            line.appendChild(element('span', 'player-outcome', label));
            line.appendChild(element('span', '', modeLabel(match.mode)));
            line.appendChild(element('span', '', formatDate(match.date)));
            history.appendChild(line);
        });
        card.appendChild(history);
        return card;
    }

    function render() {
        const query = normalize(search.value.trim());
        const filtered = players.filter(function(player) {
            return normalize(player.name).includes(query) &&
                (activeFilter === 'all' || (activeFilter === 'opponent' && player.relations.includes('opponent')) ||
                 (activeFilter === 'ally' && player.relations.includes('ally')) ||
                 (activeFilter === 'hunter' && player.roles.includes('hunter')) ||
                 (activeFilter === 'victory' && player.victories > 0) ||
                 (activeFilter === 'defeat' && player.defeats > 0));
        });
        filtered.sort(function(a, b) {
            if (sort.value === 'matches' && a.total !== b.total) return b.total - a.total;
            if (sort.value === 'name') return a.name.localeCompare(b.name, undefined, {sensitivity: 'base'});
            return b.last_seen.localeCompare(a.last_seen) || a.name.localeCompare(b.name);
        });
        document.getElementById('players_result_count').textContent = window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('players_shown', 'Joueurs affichés') + ' : ' + filtered.length : filtered.length + (filtered.length === 1 ? ' joueur' : ' joueurs');
        list.replaceChildren();
        if (!filtered.length) {
            list.appendChild(element('div', 'players-empty tracker-frame', players.length ?
                tr('no_players_match', 'Aucun joueur ne correspond à cette recherche.') :
                tr('no_players_yet', 'Aucun joueur identifié pour le moment. Les pseudos apparaîtront ici lorsqu’ils seront reconnus en jeu.')));
            return;
        }
        const fragment = document.createDocumentFragment();
        filtered.forEach(player => fragment.appendChild(playerCard(player)));
        list.appendChild(fragment);
    }

    function renderNotice() {
        let notice = unnamedCaptures ?
            (window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('unnamed_captures', 'Captures sans pseudo reconnu :') + ' ' + unnamedCaptures :
             unnamedCaptures + (unnamedCaptures === 1 ? ' capture sans pseudo reconnu n’apparaît pas dans ce journal.' : ' captures sans pseudo reconnu n’apparaissent pas dans ce journal.')) :
            tr('player_info_notice', 'Bilan établi à partir des pseudos reconnus en jeu.');
        if (players.some(player => player.history.some(match => match.event === 'summoning'))) {
            notice += ' ' + tr('hunter_notice', 'Une invocation observée ne confirme pas l’arrivée du chasseur.');
        }
        if (players.some(player => player.steam)) {
            notice += ' ' + tr('steam_separate_notice', 'Les profils Steam sont affichés séparément des personnages tant que leur correspondance n’est pas confirmée.');
        }
        document.getElementById('players_notice').textContent = notice;
    }
    document.addEventListener('ui-language-change', function() {
        if (!panel.hidden) { renderNotice(); render(); }
    });

    function loadPlayers() {
        const request = ++lastRequest;
        $.getJSON('/players').done(function(data) {
            if (request !== lastRequest) return;
            players = data.players;
            document.getElementById('players_count').textContent = players.length;
            document.getElementById('players_victories').textContent = players.reduce((sum, player) => sum + player.victories, 0);
            document.getElementById('players_defeats').textContent = players.reduce((sum, player) => sum + player.defeats, 0);
            unnamedCaptures = data.unnamed_captures;
            renderNotice();
            render();
        }).fail(function() {
            if (request !== lastRequest) return;
            list.replaceChildren(element('div', 'players-empty tracker-frame', tr('players_error', 'Impossible de charger les joueurs. Réessaie dans un instant.')));
        });
    }

    function closePlayers() {
        panel.hidden = true;
        menuButton.classList.remove('active');
    }

    menuButton.addEventListener('click', function() {
        if (!panel.hidden) {
            closePlayers();
            return;
        }
        ['menu_button_captures', 'menu_button_multi', 'menu_button_settings'].forEach(function(id) {
            const button = document.getElementById(id);
            if (button.classList.contains('active')) button.click();
        });
        panel.hidden = false;
        menuButton.classList.add('active');
        loadPlayers();
    });
    ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_history', 'menu_button_info', 'start'].forEach(function(id) {
        document.getElementById(id).addEventListener('click', closePlayers);
    });
    search.addEventListener('input', render);
    sort.addEventListener('change', render);
    document.querySelectorAll('.players-filter').forEach(function(button) {
        button.addEventListener('click', function() {
            activeFilter = button.dataset.filter;
            document.querySelectorAll('.players-filter').forEach(function(item) {
                const active = item === button;
                item.classList.toggle('active', active);
                item.setAttribute('aria-pressed', String(active));
            });
            render();
        });
    });
    $(document).ajaxSuccess(function(event, xhr, settings) {
        if (!panel.hidden && settings.url === '/capture') loadPlayers();
        if (settings.url === '/interval' && xhr.responseJSON && Number.isInteger(xhr.responseJSON.sightings_revision)) {
            const revision = xhr.responseJSON.sightings_revision;
            if (!panel.hidden && lastRevision !== null && revision !== lastRevision) loadPlayers();
            lastRevision = revision;
        }
    });
})();
