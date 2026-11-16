const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let now = 100000, interval, visibility;
const sent = [];
const document = {hidden: false, addEventListener: (_, callback) => { visibility = callback; }};
const context = {document, Date: {now: () => now},
    fetch: (url, options) => { sent.push({url, options}); return Promise.resolve({ok: true}); },
    setInterval: (callback, ms) => { assert.equal(ms, 480000); interval = callback; }};
vm.runInNewContext(fs.readFileSync('static/tracker-presence.js', 'utf8'), context);
assert.equal(sent.length, 1);
assert.equal(sent[0].url, '/tracker-presence/active');
assert.equal(sent[0].options.method, 'POST');
now += 1000; visibility(); assert.equal(sent.length, 1);
document.hidden = true; now += 60000; visibility(); assert.equal(sent.length, 1);
document.hidden = false; visibility(); assert.equal(sent.length, 2);
now += 480000; interval(); assert.equal(sent.length, 3);
console.log('Browser activity is signalled at startup and while a tab stays open.');
