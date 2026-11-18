const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function reader() {
    const context = {
        document: { getElementById: () => null, addEventListener() {}, querySelectorAll: () => [], documentElement: { setAttribute() {} } },
        window: { speechSynthesis: { getVoices: () => [], cancel() {}, speak() {} } },
        localStorage: { getItem: () => null, setItem() {} },
        console, setTimeout, setInterval, clearInterval,
    };
    vm.createContext(context);
    vm.runInContext(
        fs.readFileSync(path.join(__dirname, '../static/js/app.js'), 'utf8') + '\nthis.Reader = BibleReader;',
        context,
    );
    return Object.create(context.Reader.prototype);
}

test('live reading lands on the word at that point in the verse', () => {
    const app = reader();
    assert.equal(app.learnWordIndex(4, 0), 0);
    assert.equal(app.learnWordIndex(4, 0.5), 2);
    assert.equal(app.learnWordIndex(4, 0.99), 3);
    assert.equal(app.learnWordIndex(0, 0.4), -1);
});

test('non-latin words are wrapped so a gloss can sit above them', () => {
    const app = reader();
    app._escapeHtml = (value) => value;
    assert.match(app._wrapWordToken('世界'), /class="bw-word"/);
    assert.match(app._wrapWordToken('الله'), /class="bw-word"/);
    assert.equal(app._wrapWordToken(','), ',');
});
