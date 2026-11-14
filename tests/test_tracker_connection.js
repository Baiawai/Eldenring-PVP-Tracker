const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync('static/app.js', 'utf8');
const begin = source.indexOf('let monitorStatusGeneration = 0;');
const marker = 'setInterval(refreshMonitorStatus, 3000);';
const end = source.indexOf(marker, begin);
assert(begin >= 0 && end > begin);
const code = source.slice(begin, end + marker.length);

function simulate() {
    let reloads = 0, banner = null, request;
    const chain = {removeClass(){return this;}, text(){return this;}, attr(){return this;},
        remove(){return this;}, addClass(){return this;}, hasClass(){return false;}};
    function jquery() { return chain; }
    jquery.ajax = function() {
        request = {done(fn){this.ok = fn; return this;}, fail(fn){this.error = fn; return this;},
            always(fn){this.finished = fn; return this;}};
        return request;
    };
    const context = {$:jquery, window:{location:{reload(){reloads++;}}},
        document:{getElementById(){return banner;}, createElement(){return {setAttribute(){}};},
            body:{appendChild(node){banner = node;}}, addEventListener(){}},
        clearInterval(){}, setInterval(){}, stopPreviewPolling(){},
        trackingFavicon:{setRunning(){}}, runApp:1, text_active:['Start'], start_ready:true,
        sidebarTracking:false, renderSidebar(){}, appT:(key, fallback) => fallback};
    vm.createContext(context);
    vm.runInContext(code, context);
    return {context, get request(){return request;}, get banner(){return banner;}, get reloads(){return reloads;}};
}

const disconnected = simulate();
disconnected.request.ok({request:'success', running:false, instance:'old'});
disconnected.request.finished();
disconnected.context.refreshMonitorStatus();
disconnected.request.error({status:0});
disconnected.request.finished();
assert(disconnected.banner.textContent.includes('fermé ou inaccessible'));
disconnected.context.refreshMonitorStatus();
disconnected.request.ok({request:'success', running:false, instance:'new'});
assert.strictEqual(disconnected.reloads, 1);

// A restart between polls must also refresh the old session cookie.
const fastRestart = simulate();
fastRestart.request.ok({request:'success', running:false, instance:'old'});
fastRestart.request.finished();
fastRestart.context.refreshMonitorStatus();
fastRestart.request.ok({request:'success', running:false, instance:'new'});
assert.strictEqual(fastRestart.reloads, 1);

// Tabs from a server that did not yet expose an instance ID are supported too.
const upgrade = simulate();
upgrade.request.ok({request:'success', running:false});
upgrade.request.finished();
upgrade.context.refreshMonitorStatus();
upgrade.request.ok({request:'success', running:false, instance:'new'});
assert.strictEqual(upgrade.reloads, 1);
