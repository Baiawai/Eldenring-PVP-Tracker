(() => {
    'use strict';
    let lastPulse = 0;
    function pulse() {
        const now = Date.now();
        if (now - lastPulse < 30000) return;
        lastPulse = now;
        fetch('/tracker-presence/active', {method: 'POST', credentials: 'same-origin', cache: 'no-store'}).catch(() => {});
    }
    pulse();
    // Local browser signals are cheap; the Python worker limits each remote
    // presence update to five minutes independently of these checks.
    setInterval(pulse, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) pulse(); });
})();
