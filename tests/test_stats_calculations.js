const assert = require('node:assert/strict');
const stats = require('../static/stats-calculations.js');
const row = (date, result) => [0, '', result === 'win' ? 1 : 0, result === 'loss' ? 1 : 0, result === 'draw' ? 1 : 0, '', date, 'Arena'];
const now = new Date(2026, 2, 31, 15, 30);
const records = [
    row('2026-03-31 15:15:00', 'win'),
    row('2026-03-31 14:00:00', 'loss'),
    row('2026-03-30 15:00:00', 'draw'),
    row('2026-03-25 10:00:00', 'win'),
    row('2026-03-24 10:00:00', 'loss'),
    row('2026-03-02 10:00:00', 'loss'),
    row('2026-03-01 10:00:00', 'win'),
    row('2026-04-01 00:00:00', 'win'),
    row('2026-02-30 10:00:00', 'win'),
];
let data = stats.aggregate(records, '24h', now, 'fr-FR');
assert.equal(data.labels.length, 24);
assert.equal(data.total, 2);
assert.equal(data.victories.at(-1), 1);
assert.equal(data.defeats.at(-2), 1);
const boundary = stats.aggregate([
    row('2026-03-30 15:29:59', 'win'),
    row('2026-03-30 15:30:00', 'win'),
    row('2026-03-30 15:30:01', 'loss')
], '24h', now, 'fr-FR');
assert.equal(boundary.total, 1);
assert.equal(boundary.defeats[0], 1);
data = stats.aggregate(records, '48h', now, 'fr-FR');
assert.equal(data.labels.length, 48);
assert.equal(data.total, 3);
data = stats.aggregate(records, '7j', now, 'fr-FR');
assert.equal(data.labels.length, 7);
assert.equal(data.total, 4);
assert.equal(data.victories[0], 1);
data = stats.aggregate(records, '30j', now, 'fr-FR');
assert.equal(data.labels.length, 30);
assert.equal(data.total, 6);
data = stats.aggregate(records.reverse(), 'all', now, 'fr-FR');
assert.equal(data.total, 7);
assert.ok(data.labels[0].includes('2026'));
const user = Array(20).fill(0);
assert.equal(stats.winRate(user), 0);
user[2] = '2'; user[3] = '1'; user[4] = '1';
assert.equal(stats.winRate(user), 50);
assert.equal(stats.winRate(user, 'Invasion'), 66.67);
user[2] = 1; user[3] = 2; user[4] = 0;
assert.equal(stats.winRate(user), 33.33);
assert.equal(stats.parseCaptureDate('2026-02-30 12:00:00'), null);
console.log('Statistics calculations OK');
