const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8');
const begin = source.indexOf('// TABLE_LANGUAGE_START');
const end = source.indexOf('// TABLE_LANGUAGE_END');
assert(begin >= 0 && end > begin);
const context = {};
vm.runInNewContext(source.slice(begin, end), context);

const requests = [];
const applied = [];
let destroyed = 0;
function jquery() {
    return {DataTable(options) {
        if (options === undefined) return {destroy() { destroyed++; }};
        applied.push(options.language);
    }};
}
jquery.getJSON = function(url) {
    const request = {url};
    requests.push(request);
    return {done(fn) { request.resolve = fn; return this; }, fail(fn) { request.reject = fn; return this; }};
};
const setLanguage = context.createTableLanguageSetter(jquery);
setLanguage('fra');
setLanguage('spaes');
assert.equal(requests[1].url, '/static/table_spa.json');
requests[1].resolve({name:'Spanish'});
requests[0].resolve({name:'French'});
assert.equal(applied.length, 1);
assert.equal(applied[0].name, 'Spanish');
setLanguage('spaar');
assert.equal(requests[2].url, '/static/table_spa.json');
setLanguage('eng');
requests[2].resolve({name:'Stale Spanish'});
assert.equal(applied.length, 1);
assert.equal(destroyed, 2);
setLanguage('fra');
requests[3].reject();
assert.equal(destroyed, 3);
