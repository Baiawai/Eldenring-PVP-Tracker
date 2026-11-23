(function () {
    const panel = document.getElementById('players_panel');
    const menuButton = document.getElementById('menu_button_players');
    const search = document.getElementById('players_search');
    const sort = document.getElementById('players_sort');
    const list = document.getElementById('players_list');
    document.addEventListener('pointerdown', event => {
        list.querySelectorAll('.player-category-multiselect[open]').forEach(menu => {
            if (!menu.contains(event.target)) menu.open = false;
        });
    });
    let players = [];
    let activeFilter = 'all';
    let lastRequest = 0;
    let lastRevision = null;
    let unnamedCaptures = 0;
    let requestedPlayer = null;
    let snapshot = null;
    let nextOffset = 0;
    let hasMore = false;
    let loading = false;
    let totalPlayers = 0;
    let filteredCount = 0;
    let hasSummoning = false;
    let hasSteam = false;
    let searchTimer = null;
    let refreshTimer = null;
    let snapshotTarget = null;
    let restoreState = null;
    let legacyPlayers = null;
    let categories = [];
    let categoryColoursSupported = false;
    let multipleCategoriesSupported = false;
    let categoryCounts = null;
    let categoryFilter = '';
    const categoryTools = document.createElement('div');
    categoryTools.className = 'player-category-tools';
    categoryTools.innerHTML = '<div class="player-category-bar"><button type="button" class="player-category-toggle"></button><div class="player-category-tags"></div></div><form class="player-category-form" hidden><label><span></span><input type="text" maxlength="50" required></label><label class="player-category-colour"><span></span><input type="color" value="#c9a96b"></label><button type="submit"></button><button type="button" class="player-category-cancel"></button></form><p class="player-category-status" role="status"></p>';
    panel.querySelector('.players-controls').after(categoryTools);
    const categoryButton = categoryTools.querySelector('.player-category-toggle');
    const categoryForm = categoryTools.querySelector('form');
    const categoryInput = categoryForm.querySelector('input[type=text]');
    const categoryColour = categoryForm.querySelector('input[type=color]');
    const categoryStatus = categoryTools.querySelector('.player-category-status');
    const categoryTags = categoryTools.querySelector('.player-category-tags');
    const categorySelectLabel = document.createElement('label');
    categorySelectLabel.className = 'players-category-filter';
    const categorySelectText = document.createElement('span');
    const categorySelect = document.createElement('select');
    categorySelectLabel.append(categorySelectText, categorySelect);
    panel.querySelector('.players-controls').appendChild(categorySelectLabel);
    const favouritesFilter = document.createElement('button');
    favouritesFilter.type = 'button';
    favouritesFilter.className = 'players-filter';
    favouritesFilter.dataset.filter = 'favourite';
    favouritesFilter.setAttribute('aria-pressed', 'false');
    panel.querySelector('.players-filters').appendChild(favouritesFilter);
    const scrollArea = document.createElement('div');
    scrollArea.className = 'players-list-scroll';
    scrollArea.tabIndex = 0;
    list.parentNode.insertBefore(scrollArea, list);
    scrollArea.appendChild(list);
    const sentinel = document.createElement('div');
    sentinel.className = 'players-load-sentinel';
    sentinel.setAttribute('aria-hidden', 'true');
    scrollArea.appendChild(sentinel);
    const pageObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) loadNextPage();
    }, {root:scrollArea, rootMargin:'200px'}) : null;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    function setCategoryStatus(key, fallback) {
        if (!key) {
            delete categoryStatus.dataset.i18n;
            delete categoryStatus.dataset.i18nFr;
            categoryStatus.textContent = '';
            return;
        }
        categoryStatus.dataset.i18n = key;
        categoryStatus.dataset.i18nFr = fallback;
        categoryStatus.textContent = tr(key, fallback);
    }
    const categoryName = category => category.builtin || category.former_default ? ({steam_friend:tr('player_category_steam_friend', 'Ami Steam'), friend:tr('player_category_friend', 'Ami'), rival:tr('player_category_rival', 'Rival'), partner:tr('player_category_partner', 'Partenaire')})[category.id] || category.id : category.name;
    const categoryColourValue = category => /^#[0-9a-f]{6}$/i.test(category.color || '') ? category.color : ({friend:'#69c37b', rival:'#dc6a6a', partner:'#d4af37'})[category.id] || '#c9a96b';

    function categoryOptions(select, selected, all) {
        select.replaceChildren();
        if (!select.multiple) {
            const first = document.createElement('option');
            first.value = '';
            first.textContent = all ? tr('history_all_categories', 'Toutes les catégories') : tr('player_category_none', 'Aucune catégorie');
            select.appendChild(first);
        }
        categories.forEach(category => {
            const option = document.createElement('option');
            option.value = category.id;
            option.textContent = categoryName(category);
            if (select.multiple) option.selected = Array.isArray(selected) && selected.includes(category.id);
            select.appendChild(option);
        });
        if (!select.multiple) select.value = selected || '';
    }

    function translateCategoryTools() {
        categoryButton.textContent = tr('player_category_create', 'Créer une catégorie');
        categoryForm.querySelector('label span').textContent = tr('player_category_name', 'Nom de la catégorie');
        categoryForm.querySelector('.player-category-colour span').textContent = tr('player_category_color', 'Couleur');
        categoryForm.querySelector('[type=submit]').textContent = tr('profile_legend_save', 'Enregistrer');
        categoryForm.querySelector('.player-category-cancel').textContent = tr('online_cancel', 'Annuler');
        categorySelectText.textContent = tr('history_category', 'Catégorie');
        favouritesFilter.textContent = tr('player_favourites', 'Favoris');
        categoryOptions(categorySelect, categoryFilter, true);
        renderCategoryTags();
    }

    function renderCategoryTags() {
        categoryTags.replaceChildren();
        categories.forEach(category => {
            const pill = document.createElement('span');
            pill.className = 'player-category-pill';
            pill.style.setProperty('--category-colour', category.id === 'steam_friend' ? '#4d99c2' : categoryColourValue(category));
            const tag = document.createElement('button');
            tag.type = 'button';
            tag.className = 'player-category-tag';
            tag.dataset.categoryId = category.id;
            tag.setAttribute('aria-pressed', String(categoryFilter === category.id));
            const name = document.createElement('span');
            name.textContent = categoryName(category);
            const count = document.createElement('span');
            count.className = 'player-category-count';
            count.textContent = categoryCounts ? String(categoryCounts[category.id] || 0) : '–';
            tag.append(name, count);
            tag.addEventListener('click', () => {
                categoryFilter = categoryFilter === category.id ? '' : category.id;
                categorySelect.value = categoryFilter;
                requestedPlayer = null;
                renderCategoryTags();
                loadPlayers();
            });
            pill.appendChild(tag);
            if (!category.builtin) {
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'player-category-remove';
                remove.dataset.categoryId = category.id;
                remove.textContent = '×';
                remove.setAttribute('aria-label', tr('player_category_delete', 'Supprimer la catégorie') + ' : ' + categoryName(category));
                remove.title = remove.getAttribute('aria-label');
                remove.addEventListener('click', async () => {
                    const message = tr('player_category_delete_confirm', 'Supprimer la catégorie « {name} » ? Les joueurs associés seront retirés de cette catégorie, mais conserveront leurs favoris.').replace('{name}', categoryName(category));
                    if (!window.confirm(message)) return;
                    remove.disabled = true;
                    setCategoryStatus();
                    try {
                        const response = await fetch('/players/categories/' + encodeURIComponent(category.id), {method:'DELETE'});
                        if (!response.ok) throw new Error('request');
                        categories = categories.filter(item => item.id !== category.id);
                        if (categoryCounts) delete categoryCounts[category.id];
                        const wasFiltered = categoryFilter === category.id;
                        if (wasFiltered) categoryFilter = '';
                        translateCategoryTools();
                        loadPlayers(!wasFiltered);
                        categoryButton.focus();
                    } catch (_) {
                        setCategoryStatus('history_action_error', 'L’opération a échoué. Réessaie.');
                    } finally { remove.disabled = false; }
                });
                pill.appendChild(remove);
            }
            categoryTags.appendChild(pill);
        });
    }

    async function loadCategories() {
        try {
            const response = await fetch('/players/categories', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            categories = data.categories;
            categoryColoursSupported = Array.isArray(categories) && categories.some(category => category.builtin) &&
                categories.filter(category => category.builtin).every(category => /^#[0-9a-f]{6}$/i.test(category.color || ''));
            multipleCategoriesSupported = data.multi_category === true;
            categoryCounts = data.counts && typeof data.counts === 'object' ? data.counts : null;
            translateCategoryTools();
        } catch (_) {
            // Preserve already displayed categories if a refresh fails.
        }
    }
    translateCategoryTools();
    categoryButton.addEventListener('click', () => { categoryForm.hidden = false; setCategoryStatus(); categoryInput.focus(); });
    categoryForm.querySelector('.player-category-cancel').addEventListener('click', () => { categoryForm.hidden = true; setCategoryStatus(); categoryButton.focus(); });
    categoryForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!categoryColoursSupported) {
            setCategoryStatus('online_restart_required', 'Redémarre le tracker pour activer ce réglage.');
            return;
        }
        const submit = categoryForm.querySelector('[type=submit]');
        submit.disabled = true;
        try {
            const response = await fetch('/players/categories', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:categoryInput.value, color:categoryColour.value})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            categories.push(data.category);
            if (categoryCounts) categoryCounts[data.category.id] = 0;
            translateCategoryTools();
            categoryInput.value = '';
            categoryColour.value = '#c9a96b';
            categoryForm.hidden = true;
            setCategoryStatus();
            // Rebuild the visible selectors without changing the current position.
            loadCategories().then(() => { if (!panel.hidden) loadPlayers(true); });
            categoryButton.focus();
        } catch (_) { setCategoryStatus('history_action_error', 'L’opération a échoué. Réessaie.'); }
        finally { submit.disabled = false; }
    });
    categorySelect.addEventListener('change', () => { categoryFilter = categorySelect.value; requestedPlayer = null; renderCategoryTags(); loadPlayers(); });
    const avatarQueue = [];
    const avatarJobs = new Map();
    const avatarAvailable = new Set();
    let activeAvatarJobs = 0;
    const avatarObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting && entry.target.dataset.steamAvatarId) {
                scheduleSteamAvatar(entry.target.dataset.steamAvatarId);
            }
        });
    }, {root:scrollArea, rootMargin:'100px'}) : null;

    function avatarTargets(steamId) {
        return Array.from(list.querySelectorAll('.player-emblem-steam[data-steam-avatar-id]'))
            .filter(node => node.dataset.steamAvatarId === steamId);
    }

    function showSteamAvatar(emblem, steamId) {
        if (emblem.querySelector('img')) return;
        const portrait = document.createElement('img');
        portrait.alt = '';
        portrait.loading = 'lazy';
        portrait.addEventListener('load', () => emblem.classList.add('has-avatar'));
        portrait.addEventListener('error', () => {
            portrait.remove(); emblem.classList.remove('has-avatar');
            avatarAvailable.delete(steamId);
            if (avatarObserver && emblem.isConnected) avatarObserver.observe(emblem);
        });
        portrait.src = '/players/steam-avatar/' + steamId;
        emblem.appendChild(portrait);
    }

    function scheduleSteamAvatar(steamId) {
        if (panel.hidden || !/^\d{17}$/.test(steamId)) return;
        if (avatarAvailable.has(steamId) || avatarTargets(steamId).some(node => node.classList.contains('has-avatar'))) return;
        const previous = avatarJobs.get(steamId);
        if (previous && (previous.pending || Date.now() < previous.nextAttempt)) return;
        if (avatarQueue.length >= 64) return;
        if (avatarJobs.size >= 512) {
            for (const [id, job] of avatarJobs) {
                if (!job.pending) { avatarJobs.delete(id); break; }
            }
        }
        avatarJobs.set(steamId, {pending:true, nextAttempt:0});
        avatarQueue.push(steamId);
        drainSteamAvatars();
    }

    function drainSteamAvatars() {
        while (activeAvatarJobs < 2 && avatarQueue.length) {
            const steamId = avatarQueue.shift();
            activeAvatarJobs++;
            requestSteamAvatar(steamId).finally(() => {
                activeAvatarJobs--;
                drainSteamAvatars();
            });
        }
    }

    async function requestSteamAvatar(steamId) {
        let ready = false;
        try {
            if (panel.hidden || !avatarTargets(steamId).some(node => node.isConnected)) return;
            const response = await fetch('/players/steam-avatar/request', {
                method:'POST', body:new URLSearchParams({steam_id:steamId})
            });
            if (!response.ok) return;
            const result = await response.json();
            if (result.state === 'cached') ready = true;
            else if (result.state === 'queued') {
                // Steamworks loads portraits asynchronously. Poll only while
                // the page is open, then let a later visit retry if needed.
                const deadline = Date.now() + 40000;
                while (!panel.hidden && Date.now() < deadline && avatarTargets(steamId).some(node => node.isConnected)) {
                    await new Promise(resolve => setTimeout(resolve, 2500));
                    if (panel.hidden) break;
                    const image = await fetch('/players/steam-avatar/' + steamId, {cache:'no-store'});
                    if (image.ok && (image.headers.get('content-type') || '').startsWith('image/png')) {
                        if (image.body) await image.body.cancel();
                        ready = true; break;
                    }
                    if (image.status !== 404) break;
                }
            }
            if (ready) {
                avatarAvailable.add(steamId);
                if (avatarAvailable.size > 512) avatarAvailable.delete(avatarAvailable.values().next().value);
                avatarTargets(steamId).forEach(node => showSteamAvatar(node, steamId));
            }
        } catch (_) {
            // Missing Steam, an unavailable avatar, or an older backend is
            // normal: retain the neutral placeholder without interrupting UI.
        } finally {
            const nextAttempt = Date.now() + (ready ? 0 : 120000);
            avatarJobs.set(steamId, {pending:false, nextAttempt});
            if (!ready) window.setTimeout(() => {
                if (panel.hidden || document.hidden) return;
                const area = panel.getBoundingClientRect();
                const visible = avatarTargets(steamId).some(node => {
                    const bounds = node.getBoundingClientRect();
                    return node.isConnected && bounds.bottom >= area.top - 100 && bounds.top <= area.bottom + 100;
                });
                if (visible) scheduleSteamAvatar(steamId);
            }, 120000);
        }
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function normalize(value) {
        return value.normalize('NFKC').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
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
        card.dataset.playerKey = player.steam ? 'steam:' + player.steam.id : 'game:' + normalize(player.name);
        const summary = element('summary');
        const steamId = player.steam && /^[0-9]{17}$/.test(player.steam.id) ? player.steam.id : null;
        const emblem = element('span', 'player-emblem');
        if (steamId) {
            // The portrait is decorative: the adjacent name identifies the player.
            emblem.classList.add('player-emblem-steam');
            emblem.dataset.steamAvatarId = steamId;
            emblem.setAttribute('aria-hidden', 'true');
            const placeholder = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            placeholder.setAttribute('viewBox', '0 0 64 64');
            placeholder.innerHTML = '<circle cx="32" cy="23" r="12"/><path d="M10 58c1-13 9-20 22-20s21 7 22 20z"/>';
            emblem.appendChild(placeholder);
            if (player.steam.avatar_available === true || avatarAvailable.has(steamId)) showSteamAvatar(emblem, steamId);
            else if (avatarObserver) avatarObserver.observe(emblem);
            else queueMicrotask(() => scheduleSteamAvatar(steamId));
        } else {
            const initials = Array.from(player.name.trim())[0] || '?';
            emblem.textContent = initials.toLocaleUpperCase();
        }
        const emblemWrap = element('span', 'player-emblem-wrap');
        emblemWrap.appendChild(emblem);
        summary.appendChild(emblemWrap);
        const identity = element('span', 'player-identity');
        const profileStatus = element('p', 'player-profile-status');
        profileStatus.setAttribute('role', 'status');
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
        const playerCategories = Array.isArray(player.categories) ? player.categories.slice() : (player.category ? [player.category] : []);
        const categoryBadges = element('span', 'player-custom-categories');
        function renderPlayerBadges() {
            categoryBadges.replaceChildren();
            categories.filter(item => playerCategories.includes(item.id)).forEach(item => {
                const badge = element('span', 'player-custom-category', categoryName(item));
                badge.style.setProperty('--category-colour', categoryColourValue(item));
                categoryBadges.appendChild(badge);
            });
        }
        renderPlayerBadges();
        identity.appendChild(categoryBadges);
        const activity = [];
        if (player.total) activity.push((window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('fights', 'Combats') + ' : ' + player.total : player.total + (player.total === 1 ? ' combat' : ' combats')));
        if (player.steam && ['Invasion', 'Defense'].includes(player.steam.mode)) activity.push(tr('steam_profile_unlinked', 'Personnage non confirmé'));
        if (player.sightings) activity.push((window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('sightings', 'Observations') + ' : ' + player.sightings : player.sightings + (player.sightings === 1 ? ' apparition observée' : ' apparitions observées')));
        identity.appendChild(element('span', 'player-meta', activity.join(' · ') + ' · ' + tr('last_seen', 'Dernier') + ' : ' + formatDate(player.last_seen)));
        summary.appendChild(identity);
        const record = element('span', 'player-record');
        if (player.total) {
            record.appendChild(element('span', 'win', player.victories + ' ' + tr('victories', 'Victoires')));
            record.appendChild(element('span', 'loss', player.defeats + ' ' + tr('defeats', 'Défaites')));
            if (player.draws > 0 || player.history.some(match => match.mode === 'Arena')) record.appendChild(element('span', 'draw', player.draws + ' ' + tr('draw', 'Égalités')));
        } else {
            record.appendChild(element('span', 'none', sightingLabel(player)));
        }
        const favourite = element('button', 'player-favourite');
        favourite.type = 'button';
        const favouriteIcon = document.createElement('img');
        favouriteIcon.src = '/static/icon-favourite-bronze.svg';
        favouriteIcon.alt = '';
        favourite.appendChild(favouriteIcon);
        if (player.steam && !steamId) favourite.disabled = true;
        favourite.setAttribute('aria-pressed', String(!!player.favourite));
        favourite.title = player.favourite ? tr('player_unfavourite', 'Retirer des favoris') : tr('player_favourite', 'Ajouter aux favoris');
        favourite.setAttribute('aria-label', favourite.title);
        emblemWrap.insertBefore(favourite, emblem);
        summary.appendChild(record);
        summary.appendChild(element('span', 'player-expand', '⌄'));
        card.appendChild(summary);
        const history = element('div', 'player-history');
        const personal = element('div', 'player-category-setting');
        personal.appendChild(element('span', 'player-category-label', tr('player_categories_label', 'Catégories')));
        const category = element('details', 'player-category-multiselect');
        const categoryTrigger = element('summary', 'player-category-trigger');
        const categoryMenu = element('div', 'player-category-options');
        category.append(categoryTrigger, categoryMenu);
        personal.appendChild(category);
        categories.filter(item => !item.automatic && item.id !== 'steam_friend').forEach(item => {
            const option = document.createElement('label');
            option.className = 'player-category-option';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = item.id;
            input.checked = playerCategories.includes(item.id);
            option.append(input, element('span', '', categoryName(item)));
            categoryMenu.appendChild(option);
            input.addEventListener('change', () => { updateCategoryTrigger(); queueCategorySave(selectedCategories()); });
        });
        const selectedCategories = () => Array.from(categoryMenu.querySelectorAll('input:checked'), option => option.value);
        function updateCategoryTrigger() {
            const selected = selectedCategories();
            categoryTrigger.textContent = categories.filter(item => selected.includes(item.id)).map(categoryName).join(', ') || tr('player_category_none', 'Aucune catégorie');
            categoryTrigger.title = categoryTrigger.textContent;
            categoryTrigger.setAttribute('aria-label', tr('player_categories_label', 'Catégories') + ' : ' + categoryTrigger.textContent);
        }
        updateCategoryTrigger();
        category.addEventListener('keydown', event => {
            if (event.key === 'Escape' && category.open) { event.preventDefault(); category.open = false; categoryTrigger.focus(); }
        });
        history.appendChild(personal);
        const personalStatus = element('p', 'player-category-status');
        personalStatus.setAttribute('role', 'status');
        history.appendChild(personalStatus);
        function setCategoryDisabled(disabled) {
            categoryTrigger.setAttribute('aria-disabled', String(disabled));
            categoryMenu.querySelectorAll('input').forEach(input => { input.disabled = disabled; });
            if (disabled) category.open = false;
        }
        categoryTrigger.addEventListener('click', event => { if (categoryTrigger.getAttribute('aria-disabled') === 'true') event.preventDefault(); });
        setCategoryDisabled(!multipleCategoriesSupported || !!(player.steam && !steamId));
        if (!multipleCategoriesSupported) personalStatus.textContent = tr('online_restart_required', 'Redémarre le tracker pour activer ce réglage.');
        let personalQueue = Promise.resolve();
        let pendingCategoryUpdates = 0;
        async function savePersonal(nextCategories, nextFavourite, favouriteOnly) {
            const previousCategories = playerCategories.slice();
            personalStatus.textContent = '';
            try {
                const payload = {
                    source:steamId ? 'steam' : 'game', identity:steamId || player.name,
                    category:nextCategories[0] || null, favourite:nextFavourite
                };
                if (multipleCategoriesSupported) payload.categories = nextCategories;
                const response = await fetch('/players/preferences', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                if (!response.ok) throw new Error('request');
                const automatic = playerCategories.filter(id => id === 'steam_friend' || categories.some(item => item.id === id && item.automatic));
                player.categories = automatic.concat(nextCategories);
                playerCategories.splice(0, playerCategories.length, ...player.categories);
                player.category = nextCategories[0] || null;
                player.favourite = nextFavourite;
                favourite.setAttribute('aria-pressed', String(nextFavourite));
                favourite.title = nextFavourite ? tr('player_unfavourite', 'Retirer des favoris') : tr('player_favourite', 'Ajouter aux favoris');
                favourite.setAttribute('aria-label', favourite.title);
                if (favouriteOnly) {
                    if (activeFilter === 'favourite' && !nextFavourite) scheduleRefresh();
                } else {
                    await loadCategories();
                    renderPlayerBadges();
                    if (categoryFilter && (previousCategories.includes(categoryFilter) !== playerCategories.includes(categoryFilter))) scheduleRefresh();
                }
                return true;
            } catch (_) {
                card.open = true;
                personalStatus.textContent = tr('history_action_error', 'L’opération a échoué. Réessaie.');
                return false;
            }
        }
        function queueCategorySave(nextCategories) {
            pendingCategoryUpdates++;
            personalQueue = personalQueue.then(async () => {
                const saved = await savePersonal(nextCategories, !!player.favourite, false);
                pendingCategoryUpdates--;
                if (!saved && pendingCategoryUpdates === 0) {
                    categoryMenu.querySelectorAll('input').forEach(input => { input.checked = playerCategories.includes(input.value); });
                    updateCategoryTrigger();
                }
            });
        }
        favourite.addEventListener('click', event => {
            event.preventDefault(); event.stopPropagation();
            favourite.disabled = true;
            personalQueue = personalQueue.then(async () => {
                await savePersonal(playerCategories.filter(id => id !== 'steam_friend' && !categories.some(item => item.id === id && item.automatic)), !player.favourite, true);
                favourite.disabled = !!(player.steam && !steamId);
            });
        });
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
                else if (match.role === 'hunter') label = ({summoning: tr('hunter_summoning', 'Invocation de chasseur observée'), joined: tr('hunter_arrived', 'Chasseur arrivé'), left: tr('hunter_left', 'Chasseur reparti'), dismissed: tr('hunter_dismissed', 'Chasseur renvoyé'), died: tr('hunter_died', 'Chasseur mort'), completed: tr('hunter_objective_completed', 'Objectif du chasseur accompli')})[match.event] || tr('hunter_observed', 'Chasseur observé');
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
            if (Number.isSafeInteger(match.capture_id) && Array.isArray(player.capture_refs) && player.capture_refs.some(ref => ref.id === match.capture_id)) {
                const view = element('button', 'player-capture-link');
                view.type = 'button';
                view.title = tr('player_open_capture', 'Voir la capture');
                view.setAttribute('aria-label', view.title);
                const icon = document.createElement('img');
                icon.src = '/static/icon-camera-bronze.png';
                icon.alt = '';
                view.appendChild(icon);
                view.addEventListener('click', () => {
                    if (typeof window.openPlayerCapture === 'function') window.openPlayerCapture(player.capture_refs, match.capture_id);
                });
                line.appendChild(view);
            } else {
                const empty = element('span', 'player-capture-empty');
                empty.setAttribute('aria-hidden', 'true');
                line.appendChild(empty);
            }
            history.appendChild(line);
        });
        card.appendChild(history);
        return card;
    }

    function render() {
        document.getElementById('players_result_count').textContent = window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('players_shown', 'Joueurs affichés') + ' : ' + filteredCount : filteredCount + (filteredCount === 1 ? ' joueur' : ' joueurs');
        if (avatarObserver) avatarObserver.disconnect();
        list.replaceChildren();
        if (!players.length && !loading) {
            list.appendChild(element('div', 'players-empty tracker-frame', totalPlayers ?
                tr('no_players_match', 'Aucun joueur ne correspond à cette recherche.') :
                tr('no_players_yet', 'Aucun joueur identifié pour le moment. Les pseudos apparaîtront ici lorsqu’ils seront reconnus en jeu.')));
            return;
        }
        const fragment = document.createDocumentFragment();
        players.forEach(player => fragment.appendChild(playerCard(player)));
        list.appendChild(fragment);
    }

    function renderNotice() {
        let notice = unnamedCaptures ?
            (window.uiCurrentLanguage && window.uiCurrentLanguage() !== 'fra' ? tr('unnamed_captures', 'Captures sans pseudo reconnu :') + ' ' + unnamedCaptures :
             unnamedCaptures + (unnamedCaptures === 1 ? ' capture sans pseudo reconnu n’apparaît pas dans ce journal.' : ' captures sans pseudo reconnu n’apparaissent pas dans ce journal.')) :
            tr('player_info_notice', 'Bilan établi à partir des pseudos reconnus en jeu.');
        if (hasSummoning) notice += ' ' + tr('hunter_notice', 'Une invocation observée ne confirme pas l’arrivée du chasseur.');
        if (hasSteam) notice += ' ' + tr('steam_separate_notice', 'Les profils Steam sont affichés séparément des personnages tant que leur correspondance n’est pas confirmée.');
        document.getElementById('players_notice').textContent = notice;
    }
    document.addEventListener('ui-language-change', function() {
        translateCategoryTools();
        if (!panel.hidden) { renderNotice(); render(); }
    });

    function observeNextPage() {
        if (pageObserver) {
            pageObserver.unobserve(sentinel);
            if (hasMore && !panel.hidden) pageObserver.observe(sentinel);
        } else if (hasMore && !panel.hidden && scrollArea.scrollHeight - scrollArea.scrollTop <= scrollArea.clientHeight + 200) {
            loadNextPage();
        }
    }

    function loadPlayers(restoring) {
        if (restoring === true) {
            restoreState = {count:players.length, scrollTop:scrollArea.scrollTop,
                open:new Set(Array.from(list.querySelectorAll('.player-card[open]'), card => card.dataset.playerKey))};
        } else {
            restoreState = null;
            snapshotTarget = requestedPlayer;
        }
        ++lastRequest;
        snapshot = null;
        legacyPlayers = null;
        nextOffset = 0;
        hasMore = true;
        loading = false;
        players = [];
        scrollArea.scrollTop = 0;
        if (pageObserver) pageObserver.unobserve(sentinel);
        if (avatarObserver) avatarObserver.disconnect();
        list.replaceChildren();
        loadNextPage();
    }

    async function loadNextPage() {
        if (panel.hidden || loading || !hasMore) return;
        const generation = lastRequest;
        const first = !snapshot;
        const params = new URLSearchParams({limit:'30', offset:String(nextOffset)});
        if (snapshot) params.set('snapshot', snapshot);
        else {
            params.set('q', search.value.trim());
            params.set('filter', activeFilter);
            if (categoryFilter) params.set('category', categoryFilter);
            params.set('sort', sort.value);
            if (snapshotTarget) {
                params.set('target_id', snapshotTarget.id);
                params.set('target_name', snapshotTarget.name);
                params.set('target_source', snapshotTarget.source);
            }
        }
        loading = true;
        try {
            let data;
            if (legacyPlayers !== null) {
                data = {snapshot:'legacy', players:legacyPlayers.slice(nextOffset, nextOffset + 30),
                    next_offset:Math.min(nextOffset + 30, legacyPlayers.length), has_more:nextOffset + 30 < legacyPlayers.length,
                    filtered_count:filteredCount, count:totalPlayers, unnamed_captures:unnamedCaptures,
                    has_summoning:hasSummoning, has_steam:hasSteam,
                    victories:document.getElementById('players_victories').textContent,
                    defeats:document.getElementById('players_defeats').textContent};
            } else {
                const response = await fetch('/players?' + params.toString());
                if (generation !== lastRequest || panel.hidden) return;
                if (response.status === 409 && snapshot) { loading = false; loadPlayers(true); return; }
                if (!response.ok) throw new Error('request');
                data = await response.json();
                if (generation !== lastRequest || panel.hidden) return;
            }
            // Old backends can still return their original unpaginated response.
            if (!data.snapshot) {
                const all = data.players || [];
                const query = normalize(search.value.trim());
                const target = snapshotTarget;
                legacyPlayers = all.filter(p => (normalize(p.name).includes(query) || (target && target.id && p.steam && String(p.steam.id) === target.id)) &&
                    (activeFilter === 'all' || (activeFilter === 'opponent' && p.relations.includes('opponent')) ||
                     (activeFilter === 'ally' && p.relations.includes('ally')) || (activeFilter === 'hunter' && p.roles.includes('hunter')) ||
                     (activeFilter === 'victory' && p.victories > 0) || (activeFilter === 'defeat' && p.defeats > 0) ||
                     (activeFilter === 'favourite' && p.favourite)) && (!categoryFilter || (Array.isArray(p.categories) ? p.categories.includes(categoryFilter) : p.category === categoryFilter)));
                legacyPlayers.sort((a,b) => sort.value === 'matches' && a.total !== b.total ? b.total - a.total : sort.value === 'name' ? a.name.localeCompare(b.name, undefined, {sensitivity:'base'}) : b.last_seen.localeCompare(a.last_seen) || a.name.localeCompare(b.name));
                const matches = target ? legacyPlayers.filter(p => target.id ? p.steam && String(p.steam.id) === target.id : normalize(p.name) === normalize(target.name) &&
                    (target.source === 'steam' ? !!p.steam : target.source === 'game' ? !p.steam : true)) : [];
                if (matches.length === 1) {
                    legacyPlayers.splice(legacyPlayers.indexOf(matches[0]), 1);
                    legacyPlayers.unshift(matches[0]);
                }
                totalPlayers = all.length;
                filteredCount = legacyPlayers.length;
                unnamedCaptures = data.unnamed_captures || 0;
                hasSummoning = all.some(p => p.history.some(h => h.event === 'summoning'));
                hasSteam = all.some(p => !!p.steam);
                document.getElementById('players_count').textContent = all.length;
                document.getElementById('players_victories').textContent = all.reduce((n, p) => n + p.victories, 0);
                document.getElementById('players_defeats').textContent = all.reduce((n, p) => n + p.defeats, 0);
                data = {snapshot:'legacy', players:legacyPlayers.slice(0, 30), next_offset:Math.min(30, legacyPlayers.length),
                    has_more:legacyPlayers.length > 30, filtered_count:filteredCount, count:totalPlayers,
                    unnamed_captures:unnamedCaptures, has_summoning:hasSummoning, has_steam:hasSteam,
                    victories:document.getElementById('players_victories').textContent,
                    defeats:document.getElementById('players_defeats').textContent, exact_match:matches.length === 1};
            }
            snapshot = data.snapshot;
            nextOffset = data.next_offset;
            hasMore = data.has_more;
            filteredCount = data.filtered_count;
            totalPlayers = data.count;
            unnamedCaptures = data.unnamed_captures;
            hasSummoning = data.has_summoning;
            hasSteam = data.has_steam;
            document.getElementById('players_count').textContent = data.count;
            document.getElementById('players_victories').textContent = data.victories;
            document.getElementById('players_defeats').textContent = data.defeats;
            if (first) {
                players = data.players;
                loading = false;
                renderNotice(); render();
                if (requestedPlayer && data.exact_match && list.firstElementChild) {
                    list.firstElementChild.open = true;
                    list.firstElementChild.dataset.requestedPlayer = 'true';
                    list.firstElementChild.scrollIntoView({block:'nearest'});
                }
                requestedPlayer = null;
            } else {
                players.push(...data.players);
                const fragment = document.createDocumentFragment();
                data.players.forEach(player => fragment.appendChild(playerCard(player)));
                list.appendChild(fragment);
                loading = false;
            }
            if (restoreState) {
                list.querySelectorAll('.player-card').forEach(card => {
                    if (restoreState.open.has(card.dataset.playerKey)) {
                        card.open = true;
                        restoreState.open.delete(card.dataset.playerKey);
                    }
                });
                if (hasMore && (players.length < restoreState.count || restoreState.open.size)) { queueMicrotask(loadNextPage); return; }
                scrollArea.scrollTop = restoreState.scrollTop;
                restoreState = null;
            }
            observeNextPage();
        } catch (_) {
            if (generation !== lastRequest || panel.hidden) return;
            loading = false;
            restoreState = null;
            if (first) {
                hasMore = false;
                list.replaceChildren(element('div', 'players-empty tracker-frame', tr('players_error', 'Impossible de charger les joueurs. Réessaie dans un instant.')));
            } else if (pageObserver) {
                // Keep already displayed cards; retry only when the user scrolls.
                pageObserver.unobserve(sentinel);
            }
        } finally {
            if (generation === lastRequest) loading = false;
        }
    }

    function scheduleRefresh() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(function refresh() {
            if (panel.hidden) return;
            if (loading || restoreState) { refreshTimer = setTimeout(refresh, 300); return; }
            loadPlayers(true);
        }, 250);
    }

    function closePlayers() {
        clearTimeout(refreshTimer);
        restoreState = null;
        ++lastRequest;
        panel.hidden = true;
        menuButton.classList.remove('active');
        if (pageObserver) pageObserver.unobserve(sentinel);
        if (avatarObserver) avatarObserver.disconnect();
    }

    menuButton.addEventListener('click', function() {
        if (!panel.hidden) { closePlayers(); return; }
        ['menu_button_captures', 'menu_button_multi', 'menu_button_settings'].forEach(function(id) {
            const button = document.getElementById(id);
            if (button.classList.contains('active')) button.click();
        });
        panel.hidden = false;
        menuButton.classList.add('active');
        loadCategories().then(() => { if (!panel.hidden) loadPlayers(); });
    });
    window.openEncounteredPlayer = function(name, source, id) {
        if (!name && !id) return;
        clearTimeout(searchTimer);
        requestedPlayer = {name:String(name || ''), source:source || '', id:String(id || '')};
        search.value = name || '';
        activeFilter = 'all';
        categoryFilter = '';
        categorySelect.value = '';
        renderCategoryTags();
        panel.querySelectorAll('.players-filters .players-filter').forEach(function(item) {
            const active = item.dataset.filter === 'all';
            item.classList.toggle('active', active);
            item.setAttribute('aria-pressed', String(active));
        });
        if (panel.hidden) menuButton.click();
        else loadPlayers();
    };

    // Result sentences are supplied as escaped text; create the button in the
    // DOM so player names never become executable HTML.
    function linkCombatResults(root) {
        root.querySelectorAll('.combat-result-text[data-opponent]').forEach(function(result) {
            if (result.dataset.playerLinked) return;
            result.dataset.playerLinked = 'true';
            const name = result.dataset.opponent;
            if (!name) return;
            const walker = document.createTreeWalker(result, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const index = node.data.indexOf(name);
                if (index < 0) continue;
                const link = element('button', 'encounter-player-link', name);
                link.type = 'button';
                link.addEventListener('click', () => window.openEncounteredPlayer(name, result.dataset.opponentSource));
                node.replaceWith(document.createTextNode(node.data.slice(0, index)), link, document.createTextNode(node.data.slice(index + name.length)));
                break;
            }
        });
    }
    const liveResults = document.querySelector('.cadreStats');
    if (liveResults) {
        linkCombatResults(liveResults);
        new MutationObserver(() => linkCombatResults(liveResults)).observe(liveResults, {childList:true, subtree:true});
    }
    ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_history', 'menu_button_info', 'start'].forEach(function(id) {
        document.getElementById(id).addEventListener('click', closePlayers);
    });
    search.addEventListener('input', function() {
        requestedPlayer = null;
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadPlayers, 200);
    });
    sort.addEventListener('change', function() { requestedPlayer = null; loadPlayers(); });
    scrollArea.addEventListener('scroll', function() {
        if (scrollArea.scrollHeight - scrollArea.scrollTop <= scrollArea.clientHeight + 200) loadNextPage();
    });
    panel.querySelectorAll('.players-filters .players-filter').forEach(function(button) {
        button.addEventListener('click', function() {
            activeFilter = button.dataset.filter;
            panel.querySelectorAll('.players-filters .players-filter').forEach(function(item) {
                const active = item === button;
                item.classList.toggle('active', active);
                item.setAttribute('aria-pressed', String(active));
            });
            requestedPlayer = null;
            loadPlayers();
        });
    });
    $(document).ajaxSuccess(function(event, xhr, settings) {
        if (!panel.hidden && settings.url === '/capture') scheduleRefresh();
        if (settings.url === '/interval' && xhr.responseJSON && Number.isInteger(xhr.responseJSON.sightings_revision)) {
            const revision = xhr.responseJSON.sightings_revision;
            if (!panel.hidden && lastRevision !== null && revision !== lastRevision) scheduleRefresh();
            lastRevision = revision;
        }
    });
})();
