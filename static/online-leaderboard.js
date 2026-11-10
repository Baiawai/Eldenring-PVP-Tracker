(function () {
  'use strict';
  if (window.onlineLeaderboardReady) return;
  window.onlineLeaderboardReady = true;
  const t = (key, fr) => window.uiT ? window.uiT(key, fr) : fr;
  const nav = document.querySelector('.contente_header_settings');
  const parent = document.querySelector('.cadre_settings_sub');
  if (!nav || !parent) return;
  const tab = document.createElement('button');
  tab.type = 'button'; tab.className = 'btn_menu_settings steam-peer-tab online-ranking-tab'; tab.setAttribute('menu', '7');
  tab.title = t('online_title', 'Classement en ligne');
  tab.setAttribute('aria-label', tab.title);
  tab.innerHTML = '<img src="/static/page-icon-ranking.png" alt="">';
  nav.insertBefore(tab, nav.querySelector('[menu="4"]'));
  const section = document.createElement('section');
  section.className = 'contente_settings hide online-settings'; section.setAttribute('setting', '7');
  section.innerHTML = '<div class="form_single"><label class="form_single_left" for="online_enabled" data-online="online_participate">Participer au classement</label><div class="form_single_right"><input id="online_enabled" type="checkbox"></div></div><div class="form_single online-steam-state-row"><span class="form_single_left" data-online="online_steam_status_label">Compte Steam</span><div class="form_single_right"><span id="online_steam_state" class="online-steam-state" role="status" aria-live="polite"></span></div></div><div class="form_single"><label class="form_single_left" for="online_steam" data-online="online_steam_share">Partager mon profil Steam</label><div class="form_single_right"><input id="online_steam" type="checkbox"></div></div><div class="form_single"><span class="form_single_left" data-online="online_recovery_label">Récupérer une installation</span><div class="form_single_right"><button type="button" id="online_recover" data-online="online_recovery_start">Récupérer</button></div></div>';
  const eventReview = document.createElement('div'); eventReview.className = 'form_single online-event-review'; eventReview.hidden = true;
  eventReview.innerHTML = '<span class="form_single_left" data-online="online_conditions_label">Conditions du classement</span><div class="form_single_right"><button type="button" data-online="online_conditions_review">Consulter</button></div>';
  section.appendChild(eventReview);
  const serverConsentReview = document.createElement('div'); serverConsentReview.className = 'form_single online-server-consent-review'; serverConsentReview.hidden = true;
  serverConsentReview.innerHTML = '<span class="form_single_left" data-online="online_conditions_label">Conditions du classement</span><div class="form_single_right"><button type="button" data-online="online_conditions_review">Consulter</button></div>';
  section.appendChild(serverConsentReview);
  const serverMove = document.createElement('div'); serverMove.className = 'form_single online-server-move'; serverMove.hidden = true;
  serverMove.innerHTML = '<span class="form_single_left" data-online="online_title">Classement en ligne</span><div class="form_single_right"><button type="button" data-online="online_server_move_button">Utiliser le serveur public</button></div>';
  section.appendChild(serverMove);
  const serverMoveNotice = document.createElement('p'); serverMoveNotice.className = 'online-server-move-notice'; serverMoveNotice.setAttribute('role', 'status'); serverMoveNotice.hidden = true; section.appendChild(serverMoveNotice);
  parent.appendChild(section);
  tab.addEventListener('click', () => {
    nav.querySelectorAll('.btn_menu_settings').forEach(n => n.classList.remove('active_setting'));
    tab.classList.add('active_setting'); parent.querySelectorAll('.contente_settings').forEach(n => n.classList.add('hide'));
    section.classList.remove('hide');
    const heading = nav.querySelector('.settings-section-title'); if (heading) heading.textContent = t('online_title', 'Classement en ligne');
    if (['not_configured', 'offline', 'restart_required', 'profile_required', 'server_changed', 'server_move_required', 'partial_identity', 'server_transition_blocked', 'fresh_consent_required', 'invalid_statistics', 'event_consent_required', 'event_conflict', 'server_update_required', 'delete_pending', 'language_remove_pending', 'steam_cancel_pending', 'steam_remove_pending'].includes(activeState)) { noticeAllowed = true; show(activeState); }
    if (enabled) refreshSteamConnection();
  });
  const dialog = document.createElement('dialog'); dialog.className = 'online-dialog';
  dialog.innerHTML = '<h2 id="online_dialog_title"></h2><p id="online_dialog_text" role="status" aria-live="polite"></p><input id="online_steam_code" type="text" inputmode="numeric" pattern="[0-9]{8}" maxlength="8" autocomplete="one-time-code" hidden><select id="online_recovery_select" hidden></select><div class="online-dialog-actions"><button type="button" id="online_cancel"></button><button type="button" id="online_keep"></button><button type="button" id="online_accept"></button></div>';
  dialog.setAttribute('aria-labelledby', 'online_dialog_title'); document.body.appendChild(dialog);
  const check = document.getElementById('online_enabled');
  const steamCheck = document.getElementById('online_steam');
  const steamState = document.getElementById('online_steam_state');
  const recoveryButton = document.getElementById('online_recover');
  function addHelp(input, key, fallback) {
    if (!window.attachSettingsInfo) return;
    const description = document.createElement('p');
    description.dataset.i18n = key; description.dataset.i18nFr = fallback;
    description.textContent = t(key, fallback);
    window.attachSettingsInfo(input.closest('.form_single'), [description], 'settings_info_' + input.id);
  }
  addHelp(check, 'online_explain', 'La participation est facultative. Le tracker reste utilisable hors ligne.');
  addHelp(steamCheck, 'online_steam_help', 'Publie un lien vers ton compte Steam vérifié. Tu peux retirer ton accord à tout moment. Les changements sont appliqués au démarrage du tracker, à l’ouverture du classement ou lors de son actualisation.');
  addHelp(recoveryButton, 'online_recovery_help', 'Retrouve une ancienne installation associée à ton compte Steam pour conserver son score publié. Une nouvelle confirmation Steam est nécessaire ; l’accès de l’ancienne installation sera désactivé.');
  if (window.initSettingsYesNo) window.initSettingsYesNo(section);
  const mainStatus = document.createElement('p'); mainStatus.className = 'online-main-status'; mainStatus.setAttribute('role', 'status');
  const content = document.querySelector('.app-content'); if (content) content.prepend(mainStatus);
  let enabled = false, pending = false, busy = false, timer, steamConnection = 'disconnected', steamCheckGeneration = 0, lastSteamCheckAt = 0, loginGeneration = 0, loginPopup = null, startedParticipation = false, languageAllowed = false, supportsObservation = false, recoveryMode = false, transitionNonce = '';
  const fallbacks = {online_title:'Classement en ligne', online_participate:'Participer au classement', online_steam_status_label:'Compte Steam', online_steam_login:'Connecter mon compte Steam', online_steam_share:'Partager mon profil Steam', online_explain:'La participation est facultative. Le tracker reste utilisable hors ligne.', online_mode:'Mode', online_refresh:'Actualiser', online_name:'Pseudo', online_level:'Niveau', online_wins:'Victoires', online_losses:'Défaites', arena:'Arène 1v1', invasion:'Invasion', defense:'Monde envahi', online_previous:'Précédent', online_next:'Suivant'};
  function renderSteamConnection() {
    const words = {connected:['online_steam_connected','Connecté'], disconnected:['online_steam_disconnected','Connexion requise'], checking:['online_steam_checking','Vérification…'], unavailable:['online_steam_status_unavailable','Indisponible']};
    const entry = words[steamConnection] || words.disconnected;
    steamState.textContent = enabled ? t(entry[0], entry[1]) : '—';
    steamState.dataset.state = enabled ? steamConnection : 'inactive';
    steamCheck.disabled = !steamCheck.checked && (!enabled || steamConnection !== 'connected');
    recoveryButton.disabled = !enabled;
    steamCheck.dispatchEvent(new Event('tracker-setting-render'));
  }
  Object.assign(fallbacks, {online_recovery_label:'Récupérer une installation', online_recovery_start:'Récupérer', online_conditions_label:'Conditions du classement', online_conditions_review:'Consulter', online_server_move_button:'Utiliser le serveur public'});
  function translate() { document.querySelectorAll('[data-online]').forEach(n => n.textContent = t(n.dataset.online, fallbacks[n.dataset.online])); tab.title = t('online_title', fallbacks.online_title); tab.setAttribute('aria-label', tab.title); renderSteamConnection(); }
  document.addEventListener('ui-language-change', translate); translate();
  const stateWords = {
    syncing:['online_syncing','Synchronisation du classement…'], success:['online_success','Classement synchronisé.'],
    offline:['online_offline','Synchronisation indisponible. Tes statistiques restent enregistrées localement.'],
    not_configured:['online_not_configured','Serveur du classement non configuré.'],
    profile_required:['online_profile_required','Ajoute un pseudo dans ton profil avant la synchronisation.'],
    server_changed:['online_server_changed','Le serveur a changé. Rétablis le serveur précédent ou retire les données avant de changer de serveur.'],
    server_move_required:['online_server_move_required','Une ancienne connexion utilise un autre serveur. Utilise « Utiliser le serveur public » pour continuer sans la supprimer.'],
    partial_identity:['online_server_identity_incomplete','L’ancienne connexion est incomplète et reste conservée. Contacte l’assistance avant de changer de serveur.'],
    server_transition_blocked:['online_server_move_blocked','Arrête le suivi. Les données en attente sont conservées. Si des opérations restent liées à l’ancien serveur, utilise son environnement de développement ou contacte l’assistance.'],
    fresh_consent_required:['online_server_consent_required','Accepte de nouveau les conditions pour utiliser le classement public.'],
    invalid_statistics:['online_invalid_stats','Les statistiques ne peuvent pas être synchronisées.'],
    event_conflict:['online_event_conflict','Des événements ne peuvent pas être synchronisés. Les données restent locales ; contacte le support.'],
    event_consent_required:['online_event_consent_required','Accepte les nouvelles conditions pour reprendre la synchronisation du classement.'],
    server_update_required:['online_server_update_required','Le serveur du classement doit être mis à jour pour recevoir les combats.'],
    delete_pending:['online_delete_pending','Demande en attente : une nouvelle tentative sera effectuée au prochain démarrage.'],
    language_remove_pending:['online_delete_pending','Demande en attente : une nouvelle tentative sera effectuée au prochain démarrage.'],
    steam_cancel_pending:['online_delete_pending','Demande en attente : une nouvelle tentative sera effectuée au prochain démarrage.'],
    steam_remove_pending:['online_steam_remove_pending','Retrait du lien vers le profil Steam en attente de la prochaine synchronisation réussie.'],
    steam_login_required:['online_steam_login_required','Connecte ton compte Steam pour participer au classement.'],
    restart_required:['online_restart_required','Redémarre le tracker pour activer ce réglage.'],
    deleted:['online_deleted','Données retirées du classement.'], disabled:['online_disabled','Participation désactivée.']
  };
  let successMessageTimer, noticeFadeTimer, refreshCountdownTimer, syncNotice = '', rankingLoading = false, activeState = '';
  let noticeAllowed = true, noticeEpoch = 0;
  let serverCooldownUntil = 0, refreshNoticeUntil = 0;
  function updateServerCooldown(result) {
    if (result && Number.isFinite(result.retry_after_ms) && result.retry_after_ms >= 0) {
      serverCooldownUntil = Date.now() + result.retry_after_ms;
    }
  }
  function renderNotice() {
    const remaining = Math.max(0, Math.ceil((refreshNoticeUntil - Date.now()) / 1000));
    const countdown = remaining ? t('online_refresh_countdown', 'Prochaine actualisation dans {seconds} s.').replace('{seconds}', String(remaining)) : '';
    const value = noticeAllowed ? (countdown || syncNotice || (rankingLoading ? t('leaderboard_loading', 'Chargement du classement…') : '')) : '';
    if (value) {
      clearTimeout(noticeFadeTimer);
      mainStatus.classList.remove('is-leaving');
      mainStatus.textContent = value;
    } else if (mainStatus.textContent && !mainStatus.classList.contains('is-leaving')) {
      mainStatus.classList.add('is-leaving');
      noticeFadeTimer = setTimeout(() => {
        mainStatus.textContent = '';
        mainStatus.classList.remove('is-leaving');
      }, 400);
    }
  }
  function showRefreshCountdown(deadline, onComplete) {
    clearInterval(refreshCountdownTimer);
    refreshNoticeUntil = deadline;
    function tick() {
      if (Date.now() >= refreshNoticeUntil) {
        clearInterval(refreshCountdownTimer);
        refreshNoticeUntil = 0;
        if (onComplete) { onComplete(); return; }
      }
      renderNotice();
    }
    tick();
    if (refreshNoticeUntil) refreshCountdownTimer = setInterval(tick, 250);
  }
  function show(state) {
    activeState = state;
    clearTimeout(successMessageTimer);
    const entry = stateWords[state]; const value = entry ? t(entry[0], entry[1]) : '';
    syncNotice = noticeAllowed && (enabled || !['disabled', 'syncing', 'success'].includes(state)) ? value : '';
    renderNotice();
    if (state === 'success') successMessageTimer = setTimeout(() => {
      syncNotice = '';
      if (activeState === 'success') activeState = '';
      renderNotice();
    }, 2000);
  }
  async function call(path, options) {
    const r = await fetch('/online-leaderboard/' + path, options);
    if (!r.ok) {
      if (r.status === 404 || r.status === 405) throw Error('restart_required');
      const details = await r.json().catch(() => ({}));
      throw Error(['not_configured', 'pending_events', 'active_match', 'pending_operations', 'invalid_data', 'tracking_running', 'fresh_consent_required'].includes(details.error) ? details.error : 'request');
    }
    return r.json();
  }
  function steamStep(step) {
    dialog.dataset.action = 'steam'; dialog.dataset.step = step;
    document.getElementById('online_dialog_title').textContent = step === 'success' ? t('online_steam_connected', 'Connecté') : t('online_steam_waiting', 'Connexion à Steam');
    const messages = {
      ready: ['online_steam_login_required', 'Connecte ton compte Steam pour participer au classement.'],
      waiting: ['online_steam_waiting_code', 'Termine la connexion dans la fenêtre Steam, puis saisis ici le code à 8 chiffres affiché sur la page.'],
      closed: ['online_steam_closed', 'La fenêtre Steam a été fermée avant la fin de la connexion.'],
      blocked: ['online_steam_blocked', 'Le navigateur a bloqué la fenêtre Steam. Autorise les fenêtres pour le tracker, puis réessaie.'],
      offline: ['online_offline', 'Synchronisation indisponible. Tes statistiques restent enregistrées localement.'],
      not_configured: ['online_not_configured', 'Serveur du classement non configuré.'],
      restart_required: ['online_restart_required', 'Redémarre le tracker pour activer ce réglage.'],
      success: ['steam_page_success', 'Ton compte Steam est connecté au tracker.'],
      code: ['online_steam_code_help', 'Saisis le code affiché sur la page Steam pour confirmer la connexion.'],
      invalid_code: ['online_steam_code_invalid', 'Code invalide ou expiré. Vérifie-le ou recommence la connexion.'],
      recovery_choose: ['online_recovery_choose', 'Choisis une ancienne installation. Son ancien accès sera désactivé ; son score déjà publié sera conservé.'],
      recovery_empty: ['online_recovery_empty', 'Aucune autre installation publiée n’a été trouvée pour ce compte Steam.'],
      recovery_done: ['online_recovery_done', 'Installation récupérée. Les événements en attente seront envoyés à la prochaine synchronisation.']
    };
    const message = messages[step] || messages.offline;
    document.getElementById('online_dialog_text').textContent = t(message[0], message[1]);
    const keep = document.getElementById('online_keep');
    keep.hidden = step !== 'ready' || startedParticipation;
    if (!keep.hidden) keep.textContent = t('online_disable_title', 'Désactiver la participation');
    const cancel = document.getElementById('online_cancel'); cancel.hidden = step === 'success'; cancel.textContent = t('online_cancel', 'Annuler');
    const input = document.getElementById('online_steam_code'); input.hidden = !['waiting', 'code', 'invalid_code'].includes(step);
    const recoverySelect = document.getElementById('online_recovery_select');
    recoverySelect.hidden = step !== 'recovery_choose';
    recoverySelect.setAttribute('aria-label', t('online_recovery_placeholder', 'Choisir une installation'));
    input.setAttribute('aria-label', t('online_steam_code_label', 'Code de confirmation Steam'));
    const accept = document.getElementById('online_accept'); accept.hidden = false;
    accept.disabled = step === 'waiting' && !/^[0-9]{8}$/.test(input.value.trim());
    accept.textContent = ['success','recovery_empty','recovery_done'].includes(step) ? t('online_steam_finish', 'Terminer') : (step === 'recovery_choose' ? t('online_recovery_start', 'Récupérer') : (step === 'ready' ? t('online_steam_login', 'Connecter mon compte Steam') : (['waiting','code','invalid_code'].includes(step) ? t('online_steam_code_confirm', 'Confirmer') : t('online_steam_retry', 'Réessayer'))));
  }
  document.getElementById('online_steam_code').addEventListener('input', () => {
    if (dialog.dataset.step === 'waiting') document.getElementById('online_accept').disabled = !/^[0-9]{8}$/.test(document.getElementById('online_steam_code').value.trim());
  });
  async function refreshSteamConnection() {
    if (!enabled) { steamConnection = 'disconnected'; renderSteamConnection(); return; }
    if (steamConnection === 'checking' || (steamConnection !== 'unavailable' && Date.now() - lastSteamCheckAt < 10000)) return;
    const generation = ++steamCheckGeneration;
    lastSteamCheckAt = Date.now();
    if (steamConnection !== 'connected') { steamConnection = 'checking'; renderSteamConnection(); }
    try {
      const result = await call('steam-status?observe=1');
      if (generation !== steamCheckGeneration || !enabled) return;
      steamConnection = result.connected === true ? 'connected' : 'disconnected';
    } catch (_) {
      if (generation !== steamCheckGeneration || !enabled) return;
      steamConnection = 'unavailable';
    }
    renderSteamConnection();
  }
  async function connectSteam(popup) {
    const generation = ++loginGeneration; loginPopup = popup;
    if (!popup) { steamStep('blocked'); return; }
    steamStep('waiting');
    try {
      const existing = await call('steam-status?observe=1');
      if (typeof existing.confirmation_pending !== 'boolean') throw Error('restart_required');
      if (generation !== loginGeneration) return;
      if (existing.connected && !recoveryMode) {
        try { popup.close(); } catch (_) {}
        ++steamCheckGeneration; lastSteamCheckAt = Date.now(); steamConnection = 'connected'; startedParticipation = false; renderSteamConnection(); steamStep('success');
        if (existing.observation_only === true) await call('steam-status').catch(() => {});
        await sync();
        return;
      }
      const result = await call('steam-login', {method:'POST'});
      if (generation !== loginGeneration) return;
      // Older running backends do not forward the chosen language. The site
      // advertises support with a lang parameter in its signed return URL.
      const steamUrl = new URL(result.url);
      const callbackValue = steamUrl.searchParams.get('openid.return_to');
      if (callbackValue) {
        const callback = new URL(callbackValue);
        const language = window.uiCurrentLanguage ? window.uiCurrentLanguage() : 'fra';
        const known = ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara'];
        if (callback.searchParams.has('lang')) {
          callback.searchParams.set('lang', languageAllowed && known.includes(language) ? language : 'browser');
          steamUrl.searchParams.set('openid.return_to', callback.toString());
        }
      }
      popup.location.href = steamUrl.toString();
      for (let attempt = 0; attempt < 200; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        if (generation !== loginGeneration) return;
        const state = await call('steam-status?observe=1');
        if (generation !== loginGeneration) return;
        if (typeof state.confirmation_pending !== 'boolean') throw Error('restart_required');
        if (state.confirmation_pending === true) { steamStep('code'); document.getElementById('online_steam_code').focus(); return; }
        if (state.connected && !recoveryMode) {
          ++steamCheckGeneration; lastSteamCheckAt = Date.now(); steamConnection = 'connected'; startedParticipation = false; renderSteamConnection();
          steamStep('success');
          if (state.observation_only === true) await call('steam-status').catch(() => {});
          await sync();
          return;
        }
        if (popup.closed) break;
      }
      if (generation === loginGeneration) { steamConnection = 'disconnected'; renderSteamConnection(); steamStep('closed'); }
    } catch (error) {
      if (generation !== loginGeneration) return;
      try { popup.close(); } catch (_) {}
      steamConnection = 'unavailable'; renderSteamConnection();
      steamStep(error.message === 'restart_required' || error.message === 'not_configured' ? error.message : 'offline');
    }
  }
  async function settings(showCompleted = true) {
    try { const s = await call('settings'); updateServerCooldown(s); transitionNonce = typeof s.transition_nonce === 'string' ? s.transition_nonce : ''; serverMove.hidden = s.migration_available !== true; serverConsentReview.hidden = s.server_consent_required !== true || s.transition_blocked === true; enabled = s.enabled; eventReview.hidden = s.server_consent_required === true || !(enabled && s.event_consent_pending); supportsObservation = s.steam_status_observe === true; if (typeof s.language_shared === 'boolean') languageAllowed = s.language_shared; pending = s.state === 'delete_pending'; steamCheck.checked = s.steam_consent === true; check.checked = enabled; check.dispatchEvent(new Event('tracker-setting-render')); if (enabled && s.configured !== false && supportsObservation && s.server_consent_required !== true) refreshSteamConnection(); else { ++steamCheckGeneration; if (!enabled) steamConnection = 'disconnected'; else if (s.configured === false || s.server_consent_required === true) steamConnection = 'unavailable'; else if (s.state === 'success') steamConnection = 'connected'; else if (steamConnection === 'checking') steamConnection = 'unavailable'; renderSteamConnection(); } show(s.partial_identity === true ? 'partial_identity' : (s.transition_blocked === true ? 'server_transition_blocked' : (s.migration_available === true ? 'server_move_required' : (s.server_consent_required === true ? 'fresh_consent_required' : (enabled && s.configured === false ? 'not_configured' : (s.steam_remove_pending && s.state !== 'syncing' ? 'steam_remove_pending' : (!showCompleted && s.state === 'success' ? '' : s.state))))))); return s; } catch (_) { return null; }
  }
  async function watchSync(s) {
    show(s.state);
    while (s.state === 'syncing') { await new Promise(resolve => { timer = setTimeout(resolve, 1000); }); s = await call('status'); show(s.state); }
    await settings();
    return s;
  }
  const syncCooldownKey = 'tracker.leaderboard.last-sync-at';
  let lastSyncAttempt = 0;
  async function requestSyncWithCooldown() {
    const request = async () => {
      const now = Date.now();
      let previous = lastSyncAttempt <= now ? lastSyncAttempt : 0;
      try {
        const stored = Number(localStorage.getItem(syncCooldownKey));
        if (Number.isFinite(stored) && stored <= now) previous = Math.max(previous, stored);
      } catch (_) { /* Continue with the per-tab cooldown if storage is unavailable. */ }
      if (previous > 0 && now - previous < 10000) return {state:'rate_limited', retry_after_ms:10000 - (now - previous)};
      lastSyncAttempt = now;
      try { localStorage.setItem(syncCooldownKey, String(now)); } catch (_) { /* Per-tab fallback. */ }
      const result = await call('sync', {method:'POST'});
      updateServerCooldown(result);
      if (result.state === 'rate_limited') {
        lastSyncAttempt = previous;
        try {
          if (previous > 0) localStorage.setItem(syncCooldownKey, String(previous));
          else localStorage.removeItem(syncCooldownKey);
        } catch (_) { /* Per-tab fallback. */ }
      }
      return result;
    };
    if (navigator.locks && navigator.locks.request) return navigator.locks.request('tracker-leaderboard-sync', request);
    return request();
  }
  async function sync(showOnStart = false, waitForExisting = false) {
    if (busy) {
      if (!waitForExisting) return {state:'busy'};
      try { return await watchSync({state:'syncing'}); }
      catch (_) { show('offline'); return {state:'offline'}; }
    }
    busy = true;
    const epoch = noticeEpoch;
    try {
      const s = pending ? await call('sync', {method:'POST'}) : await requestSyncWithCooldown();
      if (s.state !== 'rate_limited') {
        if (showOnStart && epoch === noticeEpoch) noticeAllowed = true;
        return await watchSync(s);
      }
      return s;
    } catch (_) {
      if (showOnStart && epoch === noticeEpoch) noticeAllowed = true;
      show('offline');
      return {state:'offline'};
    } finally { busy = false; }
  }
  function showDialog(disabling, revalidate = false) {
    startedParticipation = false;
    recoveryMode = false;
    document.getElementById('online_steam_code').hidden = true;
    document.getElementById('online_steam_code').value = '';
    document.getElementById('online_recovery_select').hidden = true;
    document.getElementById('online_dialog_title').textContent = disabling ? t('online_disable_title','Désactiver la participation') : t('online_consent_title','Participer au classement');
    document.getElementById('online_dialog_text').textContent = disabling ? t('online_disable_text','Veux-tu conserver tes données déjà publiées dans le classement ou demander leur suppression ? La suppression sera réessayée si le serveur est indisponible.') : t('online_consent_text','La participation au classement PvP est facultative. Si tu acceptes, ton pseudo, ton niveau, ton avatar et la langue de jeu sélectionnée sont envoyés au serveur et peuvent être publiés. Un drapeau représente la langue, pas la nationalité. Tu peux arrêter de participer à tout moment.');
    if (!disabling && document.body.dataset.storeBuild === 'true') document.getElementById('online_dialog_text').textContent += ' ' + t('online_server_consent_domain', 'Le classement public est hébergé sur https://eldenringpvp.com.');
    if (!disabling) document.getElementById('online_dialog_text').textContent += ' ' + t('online_steam_login_required', 'Connecte ton compte Steam pour participer au classement.') + ' ' + t('online_steam_identity_consent', 'Le serveur conserve ton identifiant Steam vérifié. La publication du lien vers ton profil Steam est facultative.');
    if (!disabling) document.getElementById('online_dialog_text').textContent += ' ' + t('online_event_notice', 'Les débuts et résultats des combats, leur mode et leur date sont envoyés au serveur pour calculer le classement. Les anciens scores déjà publiés ne sont pas vérifiés. Les événements sont conservés jusqu’au retrait du profil.');
    if (!disabling) document.getElementById('online_dialog_text').textContent += ' ' + t('online_event_new_only', 'Pour une nouvelle inscription, seuls les combats détectés après accord comptent ; les anciennes statistiques locales ne sont pas importées.');
    const cancel = document.getElementById('online_cancel'); cancel.hidden = false; cancel.textContent = t('online_cancel','Annuler');
    const keep = document.getElementById('online_keep'); keep.hidden = !disabling; keep.textContent = t('online_keep','Conserver les données');
    const accept = document.getElementById('online_accept'); accept.hidden = false; accept.disabled = false; accept.textContent = disabling ? t('online_remove','Retirer les données') : t('online_accept','J’accepte');
    dialog.dataset.action = revalidate ? 'revalidate' : 'participation'; dialog.dataset.disabling = disabling ? '1' : '0'; dialog.dataset.transitionNonce = transitionNonce; dialog.showModal();
  }
  serverMove.querySelector('button').addEventListener('click', async event => {
    if (!window.confirm('https://eldenringpvp.com\n\n' + t('online_server_move_confirm', 'L’ancienne connexion restera sur ce PC. Les statistiques locales restent intactes ; les anciens combats ne seront pas transférés. Tu devras accepter les conditions et reconnecter Steam. Continuer ?'))) return;
    const button = event.currentTarget; button.disabled = true; serverMoveNotice.hidden = true;
    try {
      const result = await call('migrate-server', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirm:true})});
      if (!result || result.ok !== true) throw Error('request');
      await settings();
      serverMoveNotice.dataset.i18n = 'online_server_move_done'; serverMoveNotice.dataset.i18nFr = 'Ancienne connexion conservée. Active la participation, accepte les conditions et reconnecte Steam.';
    } catch (_) {
      serverMoveNotice.dataset.i18n = 'online_server_move_blocked'; serverMoveNotice.dataset.i18nFr = 'Arrête le suivi. Les données en attente sont conservées. Si des opérations restent liées à l’ancien serveur, utilise son environnement de développement ou contacte l’assistance.';
    } finally {
      serverMoveNotice.textContent = t(serverMoveNotice.dataset.i18n, serverMoveNotice.dataset.i18nFr); serverMoveNotice.hidden = false;
      button.disabled = false;
    }
  });
  eventReview.querySelector('button').addEventListener('click', () => showDialog(false, true));
  serverConsentReview.querySelector('button').addEventListener('click', () => showDialog(false));
  check.addEventListener('change', () => {
    check.checked = enabled; check.dispatchEvent(new Event('tracker-setting-render'));
    if (enabled && steamConnection !== 'connected') { startedParticipation = false; steamStep('ready'); dialog.showModal(); }
    else showDialog(enabled);
  });
  recoveryButton.addEventListener('click', () => {
    if (!enabled) return;
    startedParticipation = false; recoveryMode = true;
    connectSteam(window.open('', '_blank')); dialog.showModal();
  });
  steamCheck.addEventListener('change', async () => {
    const desired = steamCheck.checked; steamCheck.disabled = true;
    try {
      const response = await fetch('/online-leaderboard/steam-consent', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({consent:desired})});
      if (!response.ok) {
        if (response.status === 404 || response.status === 405) throw Error('restart_required');
        const error = await response.json().catch(() => ({}));
        throw Error(error.error || 'offline');
      }
      const result = await response.json();
      noticeAllowed = true;
      show(result.steam_remove_pending ? 'steam_remove_pending' : '');
    } catch (error) {
      steamCheck.checked = !desired;
      noticeAllowed = true;
      show(error.message === 'restart_required' ? 'restart_required' : error.message === 'steam_login_required' ? 'steam_login_required' : 'offline');
    } finally { renderSteamConnection(); }
  });
  async function cancelDialog() {
    const shouldDisable = dialog.dataset.action === 'steam' && startedParticipation;
    ++loginGeneration;
    if (loginPopup) { try { loginPopup.close(); } catch (_) {} loginPopup = null; }
    dialog.close();
    if (!shouldDisable) { if (dialog.dataset.action === 'steam') await call('steam-cancel', {method:'POST'}).catch(() => {}); return; }
    startedParticipation = false;
    try {
      const s = await call('settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:false, remove:false})});
      enabled = s.enabled; ++steamCheckGeneration; steamConnection = 'disconnected'; renderSteamConnection();
      check.checked = enabled; check.dispatchEvent(new Event('tracker-setting-render')); show(s.state);
    } catch (_) { show('offline'); }
  }
  document.getElementById('online_cancel').onclick = cancelDialog;
  dialog.addEventListener('cancel', event => { event.preventDefault(); cancelDialog(); });
  async function choose(remove, popup) {
    const turnOn = dialog.dataset.disabling !== '1';
    if (turnOn) { startedParticipation = true; loginPopup = popup; steamStep('waiting'); } else dialog.close();
    noticeAllowed = true;
    const generation = ++loginGeneration;
    try {
      const s = await call('settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:turnOn, consent:turnOn, language_consent:turnOn, event_consent:turnOn, remove:remove, transition_nonce:dialog.dataset.transitionNonce || ''})});
      if (turnOn && generation !== loginGeneration) {
        if (popup) popup.close();
        await call('settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:false, remove:false})}).catch(() => {});
        await settings();
        return;
      }
      transitionNonce = typeof s.transition_nonce === 'string' ? s.transition_nonce : ''; serverConsentReview.hidden = s.server_consent_required !== true; enabled = s.enabled; eventReview.hidden = s.server_consent_required === true || !(enabled && s.event_consent_pending); if (turnOn) languageAllowed = true; else if (typeof s.language_shared === 'boolean') languageAllowed = s.language_shared; pending = s.state === 'delete_pending'; steamCheck.checked = s.steam_consent === true; renderSteamConnection(); check.checked = enabled; check.dispatchEvent(new Event('tracker-setting-render')); show(s.state);
      if (turnOn) connectSteam(popup); else if (remove) sync();
    } catch (error) { if (popup) popup.close(); if (['pending_events', 'active_match', 'pending_operations', 'invalid_data', 'tracking_running'].includes(error.message)) { dialog.close(); noticeAllowed = true; show('server_transition_blocked'); } else if (error.message === 'fresh_consent_required') { dialog.close(); await settings(); } else if (turnOn && generation === loginGeneration) steamStep(error.message === 'not_configured' ? 'not_configured' : 'offline'); else show(pending ? 'delete_pending' : 'offline'); }
  }
  async function confirmExistingConsent() {
    dialog.close();
    try { await call('event-consent', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({consent:true})}); eventReview.hidden = true; await call('language-consent', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({consent:true})}); languageAllowed = true; sync(); }
    catch (_) { eventReview.hidden = false; show('offline'); }
  }
  document.getElementById('online_keep').onclick = () => { if (dialog.dataset.action === 'steam') { dialog.close(); showDialog(true); } else choose(false); };
  document.getElementById('online_accept').onclick = () => {
    if (dialog.dataset.action === 'revalidate') return confirmExistingConsent();
    if (dialog.dataset.action === 'steam') {
      if (['success','recovery_empty','recovery_done'].includes(dialog.dataset.step)) { startedParticipation = false; recoveryMode = false; dialog.close(); return; }
      if (dialog.dataset.step === 'recovery_choose') return recoverInstallation();
      if (['waiting','code','invalid_code'].includes(dialog.dataset.step)) return confirmSteamCode();
      return connectSteam(window.open('', '_blank'));
    }
    const disabling = dialog.dataset.disabling === '1';
    const popup = disabling ? null : window.open('', '_blank');
    choose(disabling, popup);
  };

  async function confirmSteamCode() {
    const input = document.getElementById('online_steam_code');
    const accept = document.getElementById('online_accept');
    accept.disabled = true;
    try {
      const response = await fetch('/online-leaderboard/steam-confirm', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code:input.value.trim()})});
      if (!response.ok) { steamStep(response.status === 400 ? 'invalid_code' : 'offline'); return; }
      ++loginGeneration; ++steamCheckGeneration; steamConnection = 'connected'; startedParticipation = false; renderSteamConnection();
      if (loginPopup) { try { loginPopup.close(); } catch (_) {} loginPopup = null; }
      input.value = '';
      if (recoveryMode) {
        const result = await call('steam-recovery');
        const select = document.getElementById('online_recovery_select'); select.replaceChildren();
        const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = t('online_recovery_placeholder', 'Choisir une installation'); select.appendChild(placeholder);
        (result.installations || []).forEach(item => { const option = document.createElement('option'); option.value = item.uuid; option.textContent = item.name + ' · ' + (item.updated_at || ''); select.appendChild(option); });
        steamStep(result.installations && result.installations.length ? 'recovery_choose' : 'recovery_empty');
      } else { steamStep('success'); await sync(); }
    } catch (_) { steamStep('offline'); }
    finally { accept.disabled = false; }
  }

  async function recoverInstallation() {
    const select = document.getElementById('online_recovery_select');
    if (!select.value) { select.focus(); return; }
    const accept = document.getElementById('online_accept'); accept.disabled = true;
    try {
      await call('steam-recovery', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({uuid:select.value})});
      steamStep('recovery_done');
    } catch (_) { steamStep('offline'); }
    finally { accept.disabled = false; }
  }

  // Search, ordering and pagination run on the server, with five avatars per request.
  const rankingStatus = document.getElementById('leaderboard_status');
  const rankingRefresh = document.getElementById('leaderboard_refresh');
  const rankingTable = document.getElementById('table_multi');
  const playerDialog = document.getElementById('leaderboard_player_dialog');
  const rankingHeader = document.querySelector('.leaderboard-shell .leaderboard-header');
  const rankingHeading = rankingHeader && rankingHeader.querySelector('.leaderboard-eyebrow');
  const rankingIntro = rankingHeader && rankingHeader.querySelector('.leaderboard-intro');
  const rankingContent = document.getElementById('leaderboard_content');
  const rankingContentToggle = document.getElementById('leaderboard_content_toggle');
  let rankingRequest = 0, rankingPlayers = new Map(), selectedRank = null, rankingStatusKey = '', rankingMode = 'Arena';
  // Player-provided names and avatars are hidden until the viewer chooses to see them.
  let rankingContentVisible = false;
  if (rankingContent) rankingContent.hidden = true;
  let refreshPending = false, rankingFetchPending = false, rankingSyncOperations = 0, openingRetryTimer;
  function updateRefreshButton() {
    if (rankingRefresh) rankingRefresh.disabled = !rankingContentVisible || refreshPending || rankingFetchPending || rankingSyncOperations > 0;
  }
  function reportHref(name) {
    const subject = t('leaderboard_report_subject', 'Signalement de contenu du classement');
    let body = t('leaderboard_report_body', 'Pseudo concerné :\nDescription :\n\nN’inclus aucune information sensible.');
    if (name) {
      const safeName = String(name).replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ').slice(0, 80)
        .replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]|[\uD800-\uDFFF]/g, part => part.length === 2 ? part : '\uFFFD');
      body = body.replace('\n', ' ' + safeName + '\n');
    }
    return 'mailto:gael.pitras@gmail.com?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
  }
  function updateReportLinks() {
    document.querySelectorAll('.leaderboard-report').forEach(link => { link.href = reportHref(); });
    const link = playerDialog && playerDialog.querySelector('.leaderboard-player-report');
    const player = rankingPlayers.get(selectedRank);
    if (link) link.href = reportHref(player && player.name);
  }
  function updateContentToggle() {
    if (!rankingContentToggle) return;
    const key = rankingContentVisible ? 'leaderboard_content_hide' : 'leaderboard_content_show';
    const fallback = rankingContentVisible ? 'Masquer le contenu des joueurs' : 'Afficher le contenu des joueurs';
    rankingContentToggle.dataset.i18n = key; rankingContentToggle.dataset.i18nFr = fallback;
    rankingContentToggle.textContent = t(key, fallback);
    rankingContentToggle.setAttribute('aria-pressed', String(rankingContentVisible));
  }
  if (rankingContentToggle && rankingContent) rankingContentToggle.addEventListener('click', () => {
    rankingContentVisible = !rankingContentVisible;
    rankingContent.hidden = !rankingContentVisible;
    updateContentToggle(); updateRefreshButton();
    if (rankingContentVisible) { loadRanking(); return; }
    ++rankingRequest; rankingFetchPending = false; rankingPlayers.clear(); selectedRank = null;
    if (playerDialog) {
      if (playerDialog.open) playerDialog.close();
      const name = document.getElementById('leaderboard_player_name'); if (name) name.textContent = '';
      const avatar = document.getElementById('leaderboard_player_avatar'); if (avatar) { avatar.removeAttribute('src'); avatar.hidden = true; }
      playerDialog.querySelectorAll('[data-player-stat], #leaderboard_player_rank, #leaderboard_player_level').forEach(node => { node.textContent = '—'; });
      const steamLink = playerDialog.querySelector('.leaderboard-steam-link'); if (steamLink) { steamLink.removeAttribute('href'); steamLink.hidden = true; }
    }
    updateReportLinks(); rankingMessage('', '');
    const table = currentTable(); if (table) table.clear().draw();
  });
  updateContentToggle(); updateReportLinks(); updateRefreshButton();
  const rankingModes = document.createElement('div');
  rankingModes.className = 'ranking-mode-tabs';
  rankingModes.setAttribute('role', 'group');
  rankingModes.innerHTML = '<button type="button" data-ranking-mode="Arena" data-online="arena" aria-pressed="true">Arène 1v1</button><button type="button" data-ranking-mode="Invasion" data-online="invasion" aria-pressed="false">Invasion</button><button type="button" data-ranking-mode="Defense" data-online="defense" aria-pressed="false">Monde envahi</button>';
  if (rankingHeader && rankingTable) rankingHeader.after(rankingModes);
  function updateRankingModeLabels() {
    rankingModes.setAttribute('aria-label', t('online_mode', 'Mode'));
    const active = rankingModes.querySelector('[data-ranking-mode="' + rankingMode + '"]');
    if (rankingHeading && active) rankingHeading.textContent = active.textContent;
    if (rankingIntro) rankingIntro.hidden = rankingMode !== 'Arena';
    if (playerDialog && active) playerDialog.querySelector('.leaderboard-player-eyebrow').textContent = active.textContent;
  }
  translate(); updateRankingModeLabels();
  function rankingMessage(key, fallback, announceLoading = true) {
    rankingStatusKey = key;
    rankingLoading = key === 'leaderboard_loading' && announceLoading;
    renderNotice();
    if (!rankingStatus) return;
    rankingStatus.hidden = !key || key === 'leaderboard_loading';
    rankingStatus.textContent = key && key !== 'leaderboard_loading' ? t(key, fallback) : '';
  }
  const escapeCell = value => $('<span>').text(value == null ? '—' : String(value)).html();
  const languageFlags = {fra:['fr','Français'],eng:['us','English'],deu:['de','Deutsch'],ita:['it','Italiano'],spaes:['es','Español (España)'],spaar:['mx','Español (Latinoamérica)'],por:['br','Português'],pol:['pl','Polski'],rus:['ru','Русский'],jap:['jp','日本語'],kor:['kr','한국어'],chi:['cn','简体中文'],zht:['tw','繁體中文'],tha:['th','ไทย'],ara:['ae','العربية']};
  function languageFlag(language) {
    const flag = typeof language === 'string' && Object.prototype.hasOwnProperty.call(languageFlags, language) ? languageFlags[language] : null;
    return flag ? $('<img>').attr({src:'/static/flags/' + flag[0] + '.svg', alt:flag[1], title:flag[1]}).prop('outerHTML') : '—';
  }
  function currentTable() {
    return window.jQuery && $.fn.DataTable && rankingTable ? $(rankingTable).DataTable() : null;
  }
  window.createLeaderboardTableOptions = function (language) {
    return {language: language || {}, serverSide:true, processing:true, pageLength:5, lengthChange:false,
      columnDefs:[{targets:3, orderable:false, searchable:false}], order:[[0,'asc']],
      ajax:async function (query, done) {
        if (!rankingContentVisible) { done({draw:query.draw, recordsTotal:0, recordsFiltered:0, data:[]}); return; }
        const request = ++rankingRequest, mode = rankingMode;
        const fields = ['rank','language','name',null,'level','score','victory','defeat','egality','ratio','combats'];
        const order = query.order && query.order[0] || {column:0, dir:'asc'};
        const params = new URLSearchParams({mode, page:String(Math.floor(query.start / 5) + 1), search:String(query.search.value || '').slice(0,80), sort:fields[order.column] || 'rank', direction:order.dir === 'desc' ? 'desc' : 'asc'});
        rankingFetchPending = true; updateRefreshButton(); rankingMessage('leaderboard_loading', 'Chargement du classement…');
        try {
          const result = await call('entries?' + params.toString());
          if (!rankingContentVisible || request !== rankingRequest) { done({draw:query.draw, recordsTotal:0, recordsFiltered:0, data:[]}); return; }
          if (!result || result.mode !== mode || !Array.isArray(result.entries) || result.entries.length > 5 || !Number.isSafeInteger(result.total) || !Number.isSafeInteger(result.filtered_total) || result.total < 0 || result.filtered_total < 0 || result.filtered_total > result.total || result.page !== Number(params.get('page')) || result.per_page !== 5) throw Error('invalid response');
          const players = new Map();
          const rows = result.entries.map(entry => {
            if (!Number.isSafeInteger(entry.rank) || entry.rank < 1 || players.has(entry.rank) || typeof entry.name !== 'string') throw Error('invalid player');
            players.set(entry.rank, entry);
            const stats = entry.stats || {};
            const validAvatar = typeof entry.avatar === 'string' && entry.avatar.length <= 280000 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(entry.avatar);
            const avatar = validAvatar ? $('<img alt="">').attr('src', entry.avatar).prop('outerHTML') : '<div class="fakeImageuser" aria-hidden="true"></div>';
            return [entry.rank, languageFlag(entry.language), escapeCell(entry.name), avatar, escapeCell(entry.level), escapeCell(entry.score), escapeCell(stats.victory), escapeCell(stats.defeat), escapeCell(mode === 'Arena' ? stats.egality : null), escapeCell(stats.ratio == null ? null : stats.ratio + ' %'), escapeCell(stats.combats)];
          });
          if (request === rankingRequest) { rankingPlayers = players; rankingMessage('', ''); }
          done({draw:query.draw, recordsTotal:result.total, recordsFiltered:result.filtered_total, data:rows});
        } catch (_) {
          if (request === rankingRequest) { rankingPlayers.clear(); rankingMessage('leaderboard_error', 'Impossible de charger le classement.'); }
          done({draw:query.draw, recordsTotal:0, recordsFiltered:0, data:[]});
        } finally { if (request === rankingRequest) { rankingFetchPending = false; updateRefreshButton(); } }
      }};
  };
  if (rankingTable) { const table = currentTable(); if (table) table.destroy(); $(rankingTable).DataTable(window.createLeaderboardTableOptions(window.currentLeaderboardLanguage)); }
  async function loadRanking() {
    const table = currentTable();
    if (table && table.ajax) table.ajax.reload(null, true);
  }
  function visibleRanks() {
    const table = currentTable();
    return table ? table.rows({search:'applied', order:'applied'}).data().toArray().map(row => Number(row[0])).filter(rank => rankingPlayers.has(rank)) : [];
  }
  function showPlayer(rank) {
    const entry = rankingPlayers.get(rank);
    if (!entry || !playerDialog) return;
    selectedRank = rank;
    updateReportLinks();
    const stats = entry.stats || {};
    document.getElementById('leaderboard_player_name').textContent = entry.name;
    let steamLink = playerDialog.querySelector('.leaderboard-steam-link');
    if (!steamLink) { steamLink = document.createElement('a'); steamLink.className = 'leaderboard-steam-link'; steamLink.target = '_blank'; steamLink.rel = 'noopener noreferrer'; playerDialog.querySelector('.leaderboard-player-heading').appendChild(steamLink); }
    let steamUnavailable = playerDialog.querySelector('.leaderboard-steam-unavailable');
    if (!steamUnavailable) { steamUnavailable = document.createElement('p'); steamUnavailable.className = 'leaderboard-steam-unavailable'; playerDialog.querySelector('.leaderboard-player-heading').appendChild(steamUnavailable); }
    steamLink.hidden = typeof entry.steam_id !== 'string' || !/^\d{17}$/.test(entry.steam_id) || entry.steam_id < '76561197960265729' || entry.steam_id > '76561202255233023';
    steamLink.textContent = t('steam_profile_browser', 'Ouvrir le profil Steam');
    if (!steamLink.hidden) steamLink.href = 'https://steamcommunity.com/profiles/' + entry.steam_id; else steamLink.removeAttribute('href');
    steamUnavailable.hidden = !steamLink.hidden;
    steamUnavailable.textContent = t('leaderboard_steam_not_shared', 'Ce participant n’a pas partagé son profil Steam.');
    let historyNotice = playerDialog.querySelector('.leaderboard-history-notice');
    if (!historyNotice) { historyNotice = document.createElement('p'); historyNotice.className = 'leaderboard-history-notice'; playerDialog.querySelector('.leaderboard-player-heading').appendChild(historyNotice); }
    historyNotice.hidden = entry.history_unverified !== true;
    historyNotice.textContent = t('online_history_unverified', 'Ce score comprend un historique antérieur non vérifié.');
    document.getElementById('leaderboard_player_rank').textContent = entry.rank;
    document.getElementById('leaderboard_player_level').textContent = entry.level ?? '—';
    const avatar = document.getElementById('leaderboard_player_avatar');
    const validAvatar = typeof entry.avatar === 'string' && entry.avatar.length <= 280000 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(entry.avatar);
    avatar.hidden = !validAvatar; document.getElementById('leaderboard_player_no_avatar').hidden = validAvatar;
    if (validAvatar) avatar.src = entry.avatar; else avatar.removeAttribute('src');
    const values = {victories:stats.victory, defeats:stats.defeat, draws:rankingMode === 'Arena' ? stats.egality : null, fights:stats.combats, rate:stats.ratio == null ? '—' : stats.ratio + ' %', score:entry.score, 'win-streak':stats.maxVictory, 'loss-streak':stats.maxDefeat, 'no-result':stats.noResult, 'opponent-left':stats.fight_exit, abandons:stats.abandon, 'connection-errors':stats.connexionError, 'game-closed':stats.gameExit};
    playerDialog.querySelectorAll('[data-player-stat]').forEach(node => { node.textContent = values[node.dataset.playerStat] ?? '—'; });
    const ranks = visibleRanks(), index = ranks.indexOf(rank);
    playerDialog.querySelector('.leaderboard-player-prev').disabled = index <= 0;
    playerDialog.querySelector('.leaderboard-player-next').disabled = index < 0 || index >= ranks.length - 1;
    if (!playerDialog.open) playerDialog.showModal();
  }
  function navigatePlayer(offset) {
    const ranks = visibleRanks(), index = ranks.indexOf(selectedRank);
    if (index >= 0 && ranks[index + offset] != null) showPlayer(ranks[index + offset]);
  }
  if (rankingTable) {
    $(rankingTable).on('draw.dt', function () {
      const table = currentTable();
      $(rankingTable).find('tbody tr').each(function () { const row = table.row(this).data(); if (row && rankingPlayers.has(Number(row[0]))) $(this).attr('tabindex', '0'); });
    }).on('click keydown', 'tbody tr', function (event) {
      if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
      const row = currentTable().row(this).data();
      if (row && rankingPlayers.has(Number(row[0]))) { event.preventDefault(); showPlayer(Number(row[0])); }
    });
  }
  if (playerDialog) {
    playerDialog.querySelector('.leaderboard-player-close').addEventListener('click', () => playerDialog.close());
    playerDialog.querySelector('.leaderboard-player-prev').addEventListener('click', () => navigatePlayer(-1));
    playerDialog.querySelector('.leaderboard-player-next').addEventListener('click', () => navigatePlayer(1));
    playerDialog.addEventListener('keydown', event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); navigatePlayer(event.key === 'ArrowLeft' ? -1 : 1); } });
  }
  const refreshCooldownKey = 'tracker.leaderboard.last-refresh-at';
  let lastRefreshAt = 0;
  async function refreshRanking() {
    const epoch = noticeEpoch;
    let waiting = false;
    try {
    await initialSettings;
    if (epoch !== noticeEpoch || !document.getElementById('menu_button_multi').classList.contains('active')) return;
    const attempt = () => {
      if (epoch !== noticeEpoch || !document.getElementById('menu_button_multi').classList.contains('active')) return 0;
      const now = Date.now();
      let previous = lastRefreshAt <= now ? lastRefreshAt : 0;
      try {
        for (const key of [refreshCooldownKey, syncCooldownKey]) {
          const stored = Number(localStorage.getItem(key));
          if (Number.isFinite(stored) && stored <= now) previous = Math.max(previous, stored);
        }
      } catch (_) { /* Per-tab cooldown remains available. */ }
      const deadline = Math.max(previous ? previous + 10000 : 0, serverCooldownUntil);
      noticeAllowed = true;
      if (deadline > now) return deadline;
      if (!enabled) {
        lastRefreshAt = now;
        try { localStorage.setItem(refreshCooldownKey, String(now)); } catch (_) { /* Per-tab fallback. */ }
      }
      return 0;
    };
    const deadline = navigator.locks && navigator.locks.request ? await navigator.locks.request('tracker-leaderboard-sync', attempt) : attempt();
    if (epoch !== noticeEpoch || !document.getElementById('menu_button_multi').classList.contains('active')) return;
    if (deadline) {
      waiting = true;
      showRefreshCountdown(deadline, refreshRanking);
      return;
    }
    if (enabled) {
      show('syncing');
      const result = await sync(true, true);
      if (epoch !== noticeEpoch || !document.getElementById('menu_button_multi').classList.contains('active')) return;
      if (result && result.state === 'rate_limited') {
        syncNotice = '';
        const wait = Math.max(250, Number(result.retry_after_ms) || Math.max(0, serverCooldownUntil - Date.now()) || 10000);
        waiting = true;
        showRefreshCountdown(Date.now() + wait, refreshRanking);
        return;
      }
    }
    await loadRanking(!enabled);
    } finally {
      if (!waiting) { refreshPending = false; updateRefreshButton(); }
    }
  }
  if (rankingRefresh) rankingRefresh.addEventListener('click', () => {
    if (refreshPending) return;
    clearTimeout(openingRetryTimer);
    refreshPending = true;
    updateRefreshButton();
    refreshRanking();
  });
  rankingModes.addEventListener('click', event => {
    const button = event.target.closest('[data-ranking-mode]');
    if (!button || !rankingModes.contains(button) || rankingMode === button.dataset.rankingMode) return;
    rankingMode = button.dataset.rankingMode; selectedRank = null;
    rankingModes.querySelectorAll('[data-ranking-mode]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    if (playerDialog && playerDialog.open) playerDialog.close();
    rankingPlayers.clear();
    noticeAllowed = true; updateRankingModeLabels(); loadRanking();
  });
  const mainMenu = document.querySelector('.main-menu');
  if (mainMenu) mainMenu.addEventListener('click', event => {
    if (!event.target.closest('li')) return;
    noticeEpoch++;
    clearTimeout(openingRetryTimer);
    noticeAllowed = false;
    syncNotice = '';
    rankingLoading = false;
    if (refreshNoticeUntil) { refreshPending = false; updateRefreshButton(); }
    clearInterval(refreshCountdownTimer);
    refreshNoticeUntil = 0;
    renderNotice();
  }, true);
  document.getElementById('menu_button_multi').addEventListener('click', () => {
    if (document.getElementById('menu_button_multi').classList.contains('active')) {
      const openingEpoch = noticeEpoch;
      rankingSyncOperations++;
      updateRefreshButton();
      loadRanking(false);
      const synchronizeOpening = async () => {
        if (enabled && openingEpoch === noticeEpoch && document.getElementById('menu_button_multi').classList.contains('active')) {
          const result = await sync(true, true);
          if (result && result.state === 'success' && openingEpoch === noticeEpoch && document.getElementById('menu_button_multi').classList.contains('active')) await loadRanking(false);
          else if (result && result.state === 'rate_limited' && openingEpoch === noticeEpoch) {
            openingRetryTimer = setTimeout(synchronizeOpening, Math.max(250, Number(result.retry_after_ms) || 10000));
          }
        }
      };
      initialSettings.then(synchronizeOpening).finally(() => { rankingSyncOperations--; updateRefreshButton(); });
    }
  });
  document.addEventListener('ui-language-change', () => { if (activeState) show(activeState); if (dialog.open && dialog.dataset.action === 'steam') steamStep(dialog.dataset.step); updateRankingModeLabels(); updateContentToggle(); updateReportLinks(); if (rankingStatusKey) rankingMessage(rankingStatusKey, rankingStatusKey === 'leaderboard_loading' ? 'Chargement du classement…' : 'Impossible de charger le classement.', rankingLoading); else renderNotice(); });
  window.addEventListener('focus', () => { if (supportsObservation && enabled && !(dialog.open && dialog.dataset.action === 'steam')) refreshSteamConnection(); });
  const initialSettings = settings(false);
  initialSettings.then(s => {
    if (s && (s.language_consent_pending || s.event_consent_pending)) setTimeout(() => { if (enabled && !document.querySelector('dialog[open]')) showDialog(false, true); }, 1000);
    if (s && s.state === 'syncing' && !busy) {
      busy = true;
      watchSync(s).catch(() => show('offline')).finally(() => { busy = false; });
    }
  });
})();
