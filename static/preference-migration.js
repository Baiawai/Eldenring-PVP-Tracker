(function () {
    'use strict';
    if (location.hostname !== 'elden-tracker.localhost') return;
    const keys = ['trackerDisplayPreferences', 'trackerSteamDisplayPreferences', 'trackerProfileSidebarOpen'];
    let absent;
    try {
        if (localStorage.getItem('trackerPreferencesMigrated') === '1') return;
        absent = keys.filter(key => localStorage.getItem(key) === null);
    } catch (_) { return; }
    if (!absent.length) { localStorage.setItem('trackerPreferencesMigrated', '1'); return; }
    const frame = document.createElement('iframe');
    frame.hidden = true;
    frame.src = 'http://localhost:5000/preference-migration';
    const finish = () => { frame.remove(); removeEventListener('message', receive); };
    function receive(event) {
        if (event.origin !== 'http://localhost:5000' || event.source !== frame.contentWindow || event.data?.type !== 'tracker-preferences-response') return;
        let changed = false;
        try {
            for (const key of absent) {
                const value = event.data.values?.[key];
                if (typeof value === 'string' && value.length < 4096) { localStorage.setItem(key, value); changed = true; }
            }
            localStorage.setItem('trackerPreferencesMigrated', '1');
        } catch (_) {}
        finish();
        if (changed) location.reload();
    }
    addEventListener('message', receive);
    frame.onload = () => frame.contentWindow.postMessage('tracker-preferences-request', 'http://localhost:5000');
    document.addEventListener('DOMContentLoaded', () => document.body.appendChild(frame), {once:true});
    setTimeout(finish, 5000);
})();
