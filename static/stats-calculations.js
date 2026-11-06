/* Pure aggregation for the statistics chart; dates without offsets are local. */
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root) root.TrackerStats = api;
})(typeof window !== 'undefined' ? window : null, function () {
    'use strict';
    function parseCaptureDate(value) {
        if (typeof value !== 'string') return null;
        const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value);
        if (!match) return null;
        const parts = match.slice(1).map(part => Number(part || 0));
        const date = new Date(parts[0], parts[1] - 1, parts[2], parts[3], parts[4], parts[5]);
        if (date.getFullYear() !== parts[0] || date.getMonth() !== parts[1] - 1 || date.getDate() !== parts[2] ||
            date.getHours() !== parts[3] || date.getMinutes() !== parts[4] || date.getSeconds() !== parts[5]) return null;
        return date;
    }
    function dayKey(date) {
        return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
    }
    function winRate(user, mode) {
        const numeric = index => Math.max(0, Number(user[index]) || 0);
        const wins = numeric(2), total = wins + numeric(3) + (mode && mode !== 'Arena' ? 0 : numeric(4));
        return total ? Math.round((wins / total * 100 + Number.EPSILON) * 100) / 100 : 0;
    }
    function aggregate(captures, period, now, locale) {
        now = now || new Date();
        const hourly = period === '24h' || period === '48h';
        const count = period === '24h' ? 24 : period === '48h' ? 48 : period === '30j' ? 30 : 7;
        const bins = new Map();
        const timeOptions = period === '48h' ? {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'} : {hour:'2-digit', minute:'2-digit'};
        const dateOptions = period === 'all' ? {day:'numeric', month:'short', year:'numeric'} : {day:'numeric', month:'short'};
        const formatter = new Intl.DateTimeFormat(locale || undefined, hourly ? timeOptions : dateOptions);
        function addBin(key, date) {
            bins.set(key, {date:date, victory:0, defeat:0, draw:0});
        }
        if (period !== 'all') {
            for (let i = count - 1; i >= 0; i--) {
                const date = hourly ? new Date(now.getTime() - (i + 1) * 3600000) : new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
                addBin(hourly ? i : dayKey(date), date);
            }
        }
        let total = 0;
        for (const row of captures) {
            const date = parseCaptureDate(row[6]);
            if (!date || date > now) continue;
            let key;
            if (hourly) key = Math.floor((now.getTime() - date.getTime()) / 3600000);
            else key = dayKey(date);
            if (period === 'all' && !bins.has(key)) addBin(key, new Date(date.getFullYear(), date.getMonth(), date.getDate()));
            const bin = bins.get(key);
            if (!bin) continue;
            if (Number(row[2]) === 1) bin.victory++;
            else if (Number(row[3]) === 1) bin.defeat++;
            else if (Number(row[4]) === 1) bin.draw++;
            else continue;
            total++;
        }
        const ordered = Array.from(bins.values()).sort((a, b) => a.date - b.date);
        return {labels:ordered.map(bin => formatter.format(bin.date)), victories:ordered.map(bin => bin.victory),
            defeats:ordered.map(bin => bin.defeat), draws:ordered.map(bin => bin.draw), total:total};
    }
    return {aggregate:aggregate, parseCaptureDate:parseCaptureDate, winRate:winRate};
});
