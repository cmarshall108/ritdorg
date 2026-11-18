const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    const elements = {};
    for (const id of ['ttsSettingsBtn', 'ttsSettingsOverlay', 'ttsSettingsClose',
        'ttsTestBtn', 'ttsResetBtn', 'ttsPreferServer', 'ttsVoiceEn',
        'ttsOnlineVoiceEn', 'ttsOnlineVoiceEs', 'ttsUseAI']) {
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
        play() { this.playCount = (this.playCount || 0) + 1; return Promise.resolve(); }
        pause() { this.pauseCount = (this.pauseCount || 0) + 1; }
    }
    class SpeechSynthesisUtterance { constructor(text) { this.text = text; } }
    const context = {
        document, window: { speechSynthesis: synthesis, SpeechSynthesisUtterance, Audio },
        localStorage: { getItem() { return null; }, setItem() {} },
        SpeechSynthesisUtterance,
        Audio, console, setTimeout, setInterval, clearInterval, performance,
        YT: { PlayerState: { PLAYING: 1, PAUSED: 2, ENDED: 0, CUED: 5 } },
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
    return { reader, elements, spoken, audio, voices, browser: context.window, context };
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

test('AI shortcut selects the current reading language and replaces video narration', async () => {
    const { reader, elements, audio } = setup();
    reader.collectVisibleVerses = () => [{ verse: '1', text: 'Hola.', lang: 'es' }];
    reader._fetchOnlineVoices = async () => ({
        es: [{ id: 'es-ES-ElviraNeural', default: true }],
    });
    let paused = false;
    reader.player = { getPlayerState: () => 1, pauseVideo() { paused = true; } };
    reader.isPlayerReady = true;
    await reader.useAIForCurrentReading();
    assert.equal(paused, true);
    assert.equal(elements.ttsOnlineVoiceEs.value, 'es-ES-ElviraNeural');
    assert.match(audio[0].url, /lang=es/);
    assert.match(audio[0].url, /voice=es-ES-ElviraNeural/);
});

test('AI shortcut reports unsupported languages without changing the voice', async () => {
    const { reader } = setup();
    reader.collectVisibleVerses = () => [{ lang: 'ja' }];
    reader._fetchOnlineVoices = async () => ({ en: [] });
    const messages = [];
    reader.showToast = message => messages.push(message);
    await reader.useAIForCurrentReading();
    assert.equal(reader.ttsSettings.preferServer, false);
    assert.match(messages[0], /No AI voice/);
});

test('reading and learning audio use the selected language and AI voice', () => {
    const { reader, audio, browser } = setup();
    browser.RITD_TRANSLATION_LANGUAGES = { Spanish: 'es' };
    assert.equal(reader.ttsLangFor('Spanish'), 'es');
    reader.ttsSettings.preferServer = true;
    reader.ttsSettings.onlineVoice.es = 'es-ES-ElviraNeural';
    reader._learnChapter = { target_lang: 'es' };
    reader.hearLearnUnit({ dataset: { lxPhrase: 'Hola' } });
    assert.match(audio[0].url, /lang=es/);
    assert.match(audio[0].url, /voice=es-ES-ElviraNeural/);
});

test('explicit word selection pauses server narration and resumes the same audio', async () => {
    const { reader, audio } = setup();
    reader.ttsSettings.preferServer = true;
    await reader.startTTS();
    reader.renderLearnContext = () => {};
    const unit = { classList: { add() {} } };
    reader.focusLearnUnit(unit, { hold: true, show: true });
    assert.equal(reader.ttsState, 'paused');
    assert.equal(audio[0].pauseCount, 1);
    reader.closeLearnContext(true);
    assert.equal(reader.ttsState, 'paused');
    assert.equal(reader.resumeReadingForStudy(), true);
    assert.equal(reader.ttsState, 'playing');
    assert.equal(reader.ttsAudio, audio[0]);
    assert.equal(audio[0].playCount, 2);
});

test('automatic follow does not pause narration; idle selection does not offer resume', async () => {
    const { reader } = setup();
    reader.renderLearnContext = () => {};
    const unit = { classList: { add() {} } };
    await reader.startTTS();
    reader.focusLearnUnit(unit);
    assert.equal(reader.ttsState, 'playing');
    reader.stopTTS();
    reader.focusLearnUnit(unit, { show: true });
    assert.equal(reader._studyPlayback, null);
});

test('browser pronunciation invalidates paused narration and restarts its verse safely', async () => {
    const { reader, spoken, browser } = setup();
    let cancellations = 0;
    browser.speechSynthesis.cancel = () => { cancellations++; };
    reader._learnChapter = { target_lang: 'en' };
    await reader.startTTS();
    const old = spoken[0];
    reader.pauseReadingForStudy();
    const generation = reader._ttsGen;
    reader.hearLearnUnit({ dataset: { lxPhrase: 'Hello' } });
    assert.equal(reader._ttsGen, generation + 1);
    assert.equal(reader._ttsNeedsStart, true);
    assert.equal(spoken[1].text, 'Hello');
    old.onerror({ error: 'interrupted' });
    assert.equal(reader.ttsState, 'paused');
    assert.equal(reader.resumeReadingForStudy(), true);
    assert.equal(spoken[2].text, 'A verse to read.');
    assert.equal(reader.ttsState, 'playing');
    assert.ok(cancellations >= 3);
    spoken[1].onerror({ error: 'canceled' });
    assert.equal(reader.ttsState, 'playing');
});

test('resuming stops study audio and ignores its late failure', async () => {
    const { reader, audio } = setup();
    const messages = [];
    reader.showToast = message => messages.push(message);
    reader.ttsSettings.preferServer = true;
    reader.ttsSettings.onlineVoice.en = 'en-US-AriaNeural';
    reader._learnChapter = { target_lang: 'en' };
    await reader.startTTS();
    reader.pauseReadingForStudy();
    reader.hearLearnUnit({ dataset: { lxPhrase: 'Hello' } });
    const study = audio[1];
    reader.resumeReadingForStudy();
    assert.equal(study.pauseCount, 1);
    study.onerror();
    assert.equal(messages.length, 0);
    assert.equal(audio[0].playCount, 2);
});

test('changing voices while paused stops the study phrase without resuming narration', async () => {
    const { reader, audio } = setup();
    reader.ttsSettings.preferServer = true;
    reader.ttsSettings.onlineVoice.en = 'en-US-AriaNeural';
    reader._learnChapter = { target_lang: 'en' };
    await reader.startTTS();
    reader.pauseReadingForStudy();
    reader.hearLearnUnit({ dataset: { lxPhrase: 'Hello' } });
    reader.restartTTSIfPlaying();
    assert.equal(audio[1].pauseCount, 1);
    assert.equal(reader.ttsState, 'paused');
    assert.equal(reader._ttsNeedsStart, true);
});

test('failed resume reports the error and stops reading', async () => {
    const { reader, audio } = setup();
    const messages = [];
    reader.showToast = message => messages.push(message);
    reader.ttsSettings.preferServer = true;
    await reader.startTTS();
    reader.pauseReadingForStudy();
    audio[0].play = () => Promise.reject(new Error('blocked'));
    reader.resumeReadingForStudy();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(reader.ttsState, 'idle');
    assert.ok(messages.includes('Could not resume reading'));
});

test('word study pauses or preserves paused video and resumes without toggling', () => {
    const { reader } = setup();
    let state = 1, pauses = 0, plays = 0;
    reader.player = {
        getPlayerState: () => state,
        pauseVideo() { pauses++; state = 2; },
        playVideo() { plays++; state = 1; },
    };
    reader.isPlayerReady = true;
    assert.equal(reader.pauseReadingForStudy(), true);
    assert.equal(reader.pauseReadingForStudy(), true);
    assert.equal(pauses, 1);
    assert.equal(reader.resumeReadingForStudy(), true);
    assert.equal(plays, 1);
    assert.equal(reader.resumeReadingForStudy(), false);
    assert.equal(plays, 1);
});

test('resuming from the main player clears a stale study resume action', async () => {
    const { reader } = setup();
    await reader.startTTS();
    reader.pauseReadingForStudy();
    reader.togglePlay();
    assert.equal(reader.ttsState, 'playing');
    assert.equal(reader._studyPlayback, null);
    assert.equal(reader.resumeReadingForStudy(), false);
    assert.equal(reader.ttsState, 'playing');
});
