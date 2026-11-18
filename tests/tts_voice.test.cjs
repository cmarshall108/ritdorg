const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    const elements = {};
    for (const id of ['ttsSettingsBtn', 'ttsSettingsOverlay', 'ttsSettingsClose',
        'ttsTestBtn', 'ttsResetBtn', 'ttsPreferServer', 'ttsVoiceEn',
        'ttsOnlineVoiceEn']) {
        elements[id] = {
            listeners: {},
            addEventListener(event, fn) { this.listeners[event] = fn; },
            classList: { add() {}, remove() {}, contains() { return false; } },
            setAttribute() {},
        };
    }
    const spoken = [];
    const voices = [
        { voiceURI: 'voice-one', name: 'One', lang: 'en-US' },
        { voiceURI: 'voice-two', name: 'Two', lang: 'en-US' },
    ];
    const synthesis = {
        getVoices: () => voices,
        cancel() {}, pause() {}, resume() {},
        speak(utterance) { spoken.push(utterance); },
    };
    const document = {
        getElementById: id => elements[id] || null,
        addEventListener() {},
        querySelectorAll: () => [],
        documentElement: { setAttribute() {} },
    };
    const audio = [];
    class Audio {
        constructor(url) { this.url = url; audio.push(this); }
        play() { return Promise.resolve(); }
        pause() {}
    }
    const context = {
        document, window: { speechSynthesis: synthesis, Audio },
        localStorage: { getItem() { return null; }, setItem() {} },
        SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
        Audio, console, setTimeout, setInterval, clearInterval, performance,
        YT: { PlayerState: { PLAYING: 1 } },
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/app.js'), 'utf8')
        + '\nthis.Reader = BibleReader;', context);
    const reader = Object.create(context.Reader.prototype);
    Object.assign(reader, {
        ttsSettings: { voice: { en: 'voice-two' }, onlineVoice: { en: '' }, preferServer: false },
        ttsState: 'idle', ttsQueue: [], ttsIndex: 0, playbackRate: 1,
        currentBook: 'Matthew', currentChapter: 1, syncTrans1: 'NIV', syncTrans2: 'Hebrew',
        autoAdvanceChapter: false,
        collectVisibleVerses: () => [{ verse: '1', text: 'A verse to read.', lang: 'en-US' }],
        setPlayBtnPlaying() {}, updateTTSProgress() {}, startTTSKeepalive() {},
        showToast() {},
    });
    return { reader, elements, spoken, audio, voices };
}

test('starting read-aloud honors the selected browser voice', async () => {
    const { reader, spoken, voices, audio } = setup();
    await reader.startTTS();
    assert.equal(reader.ttsMode, 'speech');
    assert.equal(spoken[0].voice, voices[1]);
    assert.equal(audio.length, 0);
});

test('selecting a voice switches provider and restarts the current verse', async () => {
    const { reader, elements, spoken, voices } = setup();
    reader.ttsSettings.preferServer = true;
    await reader.startTTS();
    reader.bindTTSSettings();
    elements.ttsVoiceEn.value = 'voice-two';
    elements.ttsVoiceEn.listeners.change();
    assert.equal(reader.ttsSettings.preferServer, false);
    assert.equal(elements.ttsPreferServer.checked, false);
    assert.equal(reader.ttsMode, 'speech');
    assert.equal(spoken[0].voice, voices[1]);
});

test('voice test uses the language of the voice just selected', () => {
    const { reader, elements, audio } = setup();
    reader.bindTTSSettings();
    elements.ttsOnlineVoiceEn.value = 'en-US-AriaNeural';
    elements.ttsOnlineVoiceEn.listeners.change();
    reader.testTTSVoice();
    assert.match(audio[0].url, /lang=en/);
    assert.match(audio[0].url, /voice=en-US-AriaNeural/);
});

test('resuming a rebuilt paused queue starts the selected voice', async () => {
    const { reader, spoken, voices } = setup();
    await reader.startTTS();
    reader.pauseTTS();
    reader.restartTTSIfPlaying();
    const before = spoken.length;
    reader.resumeTTS();
    assert.equal(spoken.length, before + 1);
    assert.equal(spoken.at(-1).voice, voices[1]);
});

test('a selected online voice replaces playing video and is used by read-aloud', () => {
    const { reader, elements, audio } = setup();
    let paused = false;
    reader.player = { getPlayerState: () => 1, pauseVideo() { paused = true; } };
    reader.isPlayerReady = true;
    reader.bindTTSSettings();
    elements.ttsOnlineVoiceEn.value = 'en-US-AriaNeural';
    elements.ttsOnlineVoiceEn.listeners.change();
    assert.equal(paused, true);
    assert.match(audio[0].url, /voice=en-US-AriaNeural/);
    reader.togglePlay();
    assert.equal(reader.ttsState, 'paused');
});

test('default voice preserves prerecorded video playback', () => {
    const { reader } = setup();
    reader.ttsSettings.voice.en = '';
    let played = false;
    reader.player = {
        getPlayerState: () => 2,
        playVideo() { played = true; },
    };
    reader.isPlayerReady = true;
    reader.clearSearchHighlight = () => {};
    reader.togglePlay();
    assert.equal(played, true);
    assert.equal(reader.ttsState, 'idle');
});

test('chapter video is cued rather than autoplayed when a voice is selected', () => {
    const { reader } = setup();
    let cued;
    reader.player = {
        cueVideoById(id) { cued = id; },
        loadVideoById() { assert.fail('video must not autoplay'); },
    };
    reader.isPlayerReady = true;
    reader.initYouTubePlayer('video-id');
    assert.equal(cued, 'video-id');
});

test('pausing while voices load still allows playback to resume', async () => {
    const { reader, spoken } = setup();
    let finish;
    reader.waitForVoices = () => new Promise(resolve => { finish = resolve; });
    const started = reader.startTTS();
    reader.pauseTTS();
    finish();
    await started;
    reader.resumeTTS();
    assert.equal(spoken.length, 1);
});

test('explicit browser voices override the online default for Hebrew', () => {
    const { reader } = setup();
    assert.equal(reader.ttsShouldForceServer('he-IL'), true);
    reader.ttsSettings.voice.he = 'hebrew-voice';
    assert.equal(reader.ttsShouldForceServer('he-IL'), false);
});

test('failed online and browser voices stop without retrying indefinitely', () => {
    const { reader, audio, spoken } = setup();
    const messages = [];
    reader.showToast = message => messages.push(message);
    reader.ttsSettings.preferServer = true;
    reader.startTTS();
    audio[0].onerror();
    assert.equal(reader.ttsMode, 'speech');
    spoken[0].onerror({ error: 'failed' });
    assert.equal(reader.ttsState, 'idle');
    assert.equal(audio.length, 1);
    assert.ok(messages.includes('Could not play the selected voice'));
});
