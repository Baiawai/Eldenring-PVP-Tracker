(() => {
    'use strict';

    const button = document.querySelector('.update-button');
    if (!button) return;
    let exitRequested = false;

    // The Store result controls the update requirement. An optional, slower
    // version lookup only enriches this screen and never unlocks the tracker.
    const version = document.getElementById('update-available-version');
    const versionLabel = document.getElementById('update-available-label');
    const deadline = Date.now() + 30000;
    async function refreshVersion() {
        if (exitRequested || !version || !versionLabel || Date.now() >= deadline) return;
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 3000);
        try {
            const response = await fetch('/store-update-status', {
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal
            });
            if (!response.ok) return;
            const status = await response.json();
            if (exitRequested) return;
            const source = status && status.version_source;
            const value = status && status.available_version;
            if ((source === 'store' || source === 'site') && typeof value === 'string' &&
                /^\d{1,5}(?:\.\d{1,5}){3}$/.test(value) &&
                !(source === 'site' && version.dataset.source === 'store')) {
                version.textContent = value;
                version.dataset.source = source;
                versionLabel.textContent = source === 'site' ? versionLabel.dataset.siteLabel : versionLabel.dataset.storeLabel;
            }
            if (status && status.lookup_pending === true && Date.now() < deadline) {
                window.setTimeout(refreshVersion, 1500);
            }
        } catch (_) {
            // The Store button still works if the optional local lookup fails.
        } finally {
            window.clearTimeout(timeout);
        }
    }
    refreshVersion();

    button.addEventListener('click', event => {
        if (exitRequested || event.defaultPrevented || event.button !== 0 ||
            event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        exitRequested = true;
        // Let the browser open the Store protocol before stopping the local server.
        window.setTimeout(() => {
            fetch('/exit', {method: 'POST', credentials: 'same-origin', keepalive: true})
                .catch(() => {});
        }, 250);
    });
})();
