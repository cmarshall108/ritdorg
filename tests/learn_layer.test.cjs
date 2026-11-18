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
        console, setTimeout, setInterval, clearInterval, performance,
    };
    vm.createContext(context);
    vm.runInContext(
        fs.readFileSync(path.join(__dirname, '../static/js/app.js'), 'utf8') + '\nthis.Reader = BibleReader;',
        context,
    );
    const app = Object.create(context.Reader.prototype);
    app.testContext = context;
    return app;
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

test('word context floats near the selected word and stays inside the viewport', () => {
    const app = reader();
    const popup = { hidden: false, offsetWidth: 200, offsetHeight: 100, style: {} };
    app.testContext.document.getElementById = id => id === 'learnContext' ? popup : null;
    Object.assign(app.testContext.window, { innerWidth: 400, innerHeight: 300 });
    app._learnContextUnit = {
        isConnected: true,
        getBoundingClientRect: () => ({ left: 380, width: 20, top: 250, bottom: 270 }),
        closest: () => ({ getBoundingClientRect: () => ({ top: 0, bottom: 300 }) }),
    };
    app.positionLearnContext();
    assert.equal(popup.style.left, '190px');
    assert.equal(popup.style.top, '140px');
    assert.equal(popup.style.visibility, '');
    app._learnContextUnit.isConnected = false;
    app.positionLearnContext();
    assert.equal(popup.hidden, true);
});

test('word context follows its anchor when focus mode changes the layout', () => {
    const app = reader();
    const popup = { hidden: false, offsetWidth: 200, offsetHeight: 100, style: {} };
    let focused = false;
    app.testContext.document.body = { classList: { toggle: (_, value) => { focused = value; } } };
    app.testContext.document.getElementById = id => id === 'learnContext' ? popup : null;
    Object.assign(app.testContext.window, { innerWidth: 600, innerHeight: 600 });
    app._scheduleSessionStateSave = () => {};
    app._learnContextUnit = {
        isConnected: true,
        getBoundingClientRect: () => ({ left: focused ? 100 : 200, width: 20, top: 100, bottom: 120 }),
        closest: () => ({ getBoundingClientRect: () => ({ top: 0, bottom: 600 }) }),
    };
    app.positionLearnContext();
    assert.equal(popup.style.left, '110px');
    app.applyFocusMode(true);
    assert.equal(popup.style.left, '10px');
});

test('learning follows the visible column of the active view', () => {
    const app = reader();
    const columns = {
        syncCol1: { classList: { contains: () => false } },
        parallelCol1: { classList: { contains: () => true } },
        parallelCol2: { classList: { contains: () => false } },
    };
    app.testContext.document.getElementById = id => columns[id] || null;
    app.syncTrans1 = 'NIV';
    app.parallelTrans1 = 'French';
    app.parallelTrans2 = 'Spanish';
    app.currentTranslation = 'German';
    app._currentViewName = () => 'parallel';
    assert.equal(app.visibleReadingTranslation(), 'Spanish');
    app._currentViewName = () => 'reader';
    assert.equal(app.visibleReadingTranslation(), 'German');
});

test('context navigation stays in the selected reading column', () => {
    const app = reader();
    const first = {};
    const second = { scrollIntoView() {} };
    const root = { querySelectorAll: () => [first, second] };
    first.closest = () => root;
    app._learnContextUnit = first;
    let focused;
    app.focusLearnUnit = unit => { focused = unit; };
    app.stepLearnWord(1);
    assert.equal(focused, second);
});

test('click and keyboard word selection pause, but follow highlighting does not', () => {
    const app = reader();
    const listeners = {};
    const button = { addEventListener() {}, setAttribute() {}, contains: () => false };
    const dock = { ...button, hidden: true };
    app.testContext.document.getElementById = id => ({ learnOpenBtn: button, learnDock: dock }[id] || null);
    app.testContext.document.addEventListener = (name, fn) => { listeners[name] = fn; };
    app.testContext.window.addEventListener = () => {};
    app.learn = { enabled: true };
    app.ttsState = 'playing';
    let pauses = 0;
    app.pauseTTS = () => { pauses++; app.ttsState = 'paused'; };
    app.renderLearnContext = () => {};
    app.populateLearnSelects = () => {};
    app.updateLearnUI = () => {};
    app.syncLearnChrome = () => {};
    app.bindLearnMode();
    const unit = { classList: { add() {} }, closest: () => unit };
    const event = { target: unit, preventDefault() {}, stopImmediatePropagation() {} };
    listeners.click(event);
    assert.equal(pauses, 1);
    app.ttsState = 'playing';
    listeners.keydown({ ...event, key: 'Enter' });
    assert.equal(pauses, 2);
    app.ttsState = 'playing';
    app.focusLearnUnit(unit);
    assert.equal(pauses, 2);
});

test('ordinary word clicks pause reading before opening study', () => {
    const app = reader();
    const listeners = {};
    class Element {}
    app.testContext.HTMLElement = Element;
    app.testContext.Node = class {};
    app.testContext.document.addEventListener = (name, fn) => { listeners[name] = fn; };
    app.testContext.window.addEventListener = () => {};
    app.ttsState = 'playing';
    app.pauseTTS = () => { app.ttsState = 'paused'; };
    let stateAtOpen;
    app.openWordPopover = () => { stateAtOpen = app.ttsState; };
    app.bindGenericWordLookup();
    const word = new Element();
    word.classList = { contains: cls => cls === 'bw-word' };
    listeners.click({ target: word, stopPropagation() {} });
    assert.equal(stateAtOpen, 'paused');
    assert.equal(app._studyPlayback, 'tts');
});

test('word study accepts words in non-Latin scripts', async () => {
    const app = reader();
    const controls = { addEventListener() {} };
    const pop = {
        setAttribute() {}, addEventListener() {},
        querySelector: () => controls,
    };
    app.testContext.document.createElement = () => pop;
    app.testContext.document.body = { appendChild() {} };
    app._translationForNode = () => 'Chinese';
    app._langForTranslation = () => 'zh';
    app._isRightSideContainer = () => false;
    app._positionPopoverNear = () => {};
    await app.openWordPopover({ textContent: '«世界»', classList: { add() {} } });
    assert.match(pop.innerHTML, /bw-popover-word">世界</);
});

function reviewReader() {
    const app = reader();
    const storage = {};
    app.testContext.localStorage = {
        getItem: key => storage[key] ?? null,
        setItem: (key, value) => { storage[key] = value; },
    };
    const ids = ['learnReviewOpen', 'learnReview', 'learnReviewStatus', 'learnReviewCard',
        'learnReviewEarly', 'learnReviewReference', 'learnReviewPrompt', 'learnReviewAnswerLabel',
        'learnReviewAnswer', 'learnReviewReveal', 'learnReviewAgain', 'learnReviewRemembered',
        'learnReviewRemove', 'learnReviewClose', 'learnReviewResume'];
    const elements = Object.fromEntries(ids.map(id => [id, { hidden: false, textContent: '', focus() {} }]));
    app.testContext.document.getElementById = id => elements[id] || null;
    app.testContext.window.confirm = () => true;
    app.currentBook = 'John';
    app.currentChapter = 3;
    app.learn = { enabled: true, native: 'NIV', target: 'Spanish' };
    app._learnKey = 'John|3|NIV|Spanish';
    app._learnChapter = { verses: { '16': { native: 'For God loved the world.', target: 'Dios amó al mundo.' } } };
    app._learnContextUnit = { closest: () => ({ dataset: { verse: '16' } }) };
    app.showToast = message => { app.messages.push(message); };
    app.messages = [];
    return { app, storage, elements };
}

test('saving uses complete verse pairs, deduplicates, and rejects stale or missing passages', () => {
    const { app, storage } = reviewReader();
    app.saveLearnVerse();
    app.saveLearnVerse();
    const cards = JSON.parse(storage.learnReviewV1);
    assert.equal(cards.length, 1);
    assert.equal(cards[0].nativeText, 'For God loved the world.');
    assert.equal(cards[0].targetText, 'Dios amó al mundo.');
    assert.match(app.messages.at(-1), /already saved/);
    app.currentChapter = 4;
    app.saveLearnVerse();
    assert.match(app.messages.at(-1), /not available/);
    assert.equal(JSON.parse(storage.learnReviewV1).length, 1);
    app.currentChapter = 3;
    app._learnChapter.verses['16'].target = '';
    app.saveLearnVerse();
    assert.match(app.messages.at(-1), /not available/);
});

test('review hides the answer until reveal and schedules self-rated recall', () => {
    const { app, storage, elements } = reviewReader();
    app.saveLearnVerse();
    app.renderLearnReview();
    assert.equal(elements.learnReviewAnswer.hidden, true);
    assert.equal(elements.learnReviewRemembered.hidden, true);
    app.gradeLearnReview(true);
    assert.equal(JSON.parse(storage.learnReviewV1)[0].stage, 0);
    app._learnReviewRevealed = true;
    app.renderLearnReview();
    assert.equal(elements.learnReviewAnswer.hidden, false);
    assert.equal(elements.learnReviewAnswer.textContent, 'Dios amó al mundo.');
    const now = Date.now();
    app.gradeLearnReview(true);
    let card = JSON.parse(storage.learnReviewV1)[0];
    assert.equal(card.stage, 1);
    assert.ok(card.due >= now + 86400000 && card.due < now + 86401000);
    assert.equal(elements.learnReviewCard.hidden, true);
    assert.equal(elements.learnReviewEarly.hidden, false);
    app._learnReviewEarly = true;
    app.renderLearnReview();
    assert.equal(elements.learnReviewAnswer.hidden, true);
    app._learnReviewRevealed = true;
    app.gradeLearnReview(false);
    card = JSON.parse(storage.learnReviewV1)[0];
    assert.equal(card.stage, 0);
    assert.ok(card.due >= now + 600000 && card.due < now + 601000);
});

test('review prioritizes due cards and allows removal without affecting others', () => {
    const { app, storage, elements } = reviewReader();
    app.saveLearnVerse();
    const cards = JSON.parse(storage.learnReviewV1);
    cards[0].due = Date.now() + 86400000;
    cards.push({ ...cards[0], id: 'another-pair', target: 'French', targetText: 'Dieu a aimé le monde.', due: Date.now() - 1 });
    storage.learnReviewV1 = JSON.stringify(cards);
    app.renderLearnReview();
    assert.equal(elements.learnReviewAnswer.textContent, 'Dieu a aimé le monde.');
    app.removeLearnReview();
    assert.equal(JSON.parse(storage.learnReviewV1).length, 1);
    assert.equal(elements.learnReviewCard.hidden, true);
    assert.equal(elements.learnReviewEarly.hidden, false);
});

test('review storage errors are reported without overwriting existing data', () => {
    const { app, storage } = reviewReader();
    storage.learnReviewV1 = '{"broken":true}';
    app.saveLearnVerse();
    assert.equal(storage.learnReviewV1, '{"broken":true}');
    assert.match(app.messages.at(-1), /Could not read/);
    delete storage.learnReviewV1;
    app.testContext.localStorage.setItem = () => { throw new Error('storage blocked'); };
    app.saveLearnVerse();
    assert.match(app.messages.at(-1), /Could not save/);
});

test('a late alignment response cannot restore an old learning selection', async () => {
    const app = reader();
    let finish;
    app.learn = { enabled: true, native: 'NIV', target: 'Spanish' };
    app.currentBook = 'John';
    app.currentChapter = 3;
    app._learnToken = 0;
    app.testContext.fetch = async () => ({
        ok: true,
        json: () => new Promise(resolve => { finish = resolve; }),
    });
    const request = app.refreshLearn();
    await new Promise(resolve => setImmediate(resolve));
    app.learn.enabled = false;
    app._learnToken++;
    finish({ verses: {} });
    await request;
    assert.equal(app._learnChapter, undefined);
});

test('an older request cannot clear a newer request for the same selection', async () => {
    const app = reader();
    const finishes = [];
    app.learn = { enabled: true, native: 'NIV', target: 'Spanish' };
    app.currentBook = 'John';
    app.currentChapter = 3;
    app._learnToken = 0;
    app.applyLearnLayer = () => {};
    app.renderLearnContext = () => {};
    app.testContext.document.querySelector = () => null;
    app.testContext.fetch = async () => ({
        ok: true,
        json: () => new Promise(resolve => finishes.push(resolve)),
    });
    const first = app.refreshLearn();
    await new Promise(resolve => setImmediate(resolve));
    const second = app.refreshLearn();
    await new Promise(resolve => setImmediate(resolve));
    finishes[0]({ verses: {} });
    await first;
    assert.equal(app._learnInflight, 'John|3|NIV|Spanish');
    finishes[1]({ verses: {} });
    await second;
    assert.equal(app._learnInflight, '');
});
