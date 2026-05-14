/* ritdorg study tools — single-file client module
 *
 * Adds a floating "Study" button that opens a tabbed panel covering all
 * 24 features added on the server side. Designed to coexist with
 * `app.js` / `userdata.js` without modifying their state.
 *
 * Tabs:
 *   - Concordance    (#1 cross-translation)
 *   - Search         (#3 phrase + filters)
 *   - Cross-refs     (#5 TSK)
 *   - Lemma bridge   (#2 + #4)
 *   - Tags           (#7)
 *   - Outlines       (#6)
 *   - Sermon list    (#8 playlists + preach view)
 *   - Reading plan   (#9 + progress)
 *   - Notebooks      (#16 shared)
 *   - Settings       (dyslexia #22, font, etc.)
 *
 * Plus globally:
 *   #10 Print/PDF — “Print handout” button
 *   #13 Audio clip — “Download clip” inside the audio bar
 *   #14 TTS cache — handled server-side; UI shows X-TTS-Cache hits
 *   #15 Footnotes — drawer auto-opens when bracketed footnotes detected
 *   #17 OG share image
 *   #18 Permalink — auto-encode/restore study state in URL hash
 *   #19 Export ZIP
 *   #20 Keyboard shortcuts — `?` opens cheat sheet
 *   #21 Read-aloud queue — uses existing speech queue + new reorder UI
 *   #22 Dyslexia mode — body class + font swap
 *   #23 PWA — service worker registration + manifest
 *   #24 Greek NT — surfaces availability if /api/corpus/availability says so
 */
(function () {
    'use strict';

    // ---- helpers --------------------------------------------------------
    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
    const html = (strings, ...vals) =>
        strings.reduce((acc, s, i) => acc + s + (vals[i] == null ? '' : String(vals[i])), '');
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

    async function api(path, opts) {
        opts = opts || {};
        const init = { credentials: 'same-origin', headers: {} };
        if (opts.method) init.method = opts.method;
        if (opts.body !== undefined) {
            init.body = JSON.stringify(opts.body);
            init.headers['Content-Type'] = 'application/json';
        }
        const r = await fetch(path, init);
        if (!r.ok) {
            let detail = '';
            try { detail = (await r.json()).error || ''; } catch (_) { /* */ }
            throw new Error(detail || ('HTTP ' + r.status));
        }
        const ct = r.headers.get('content-type') || '';
        return ct.includes('application/json') ? r.json() : r.text();
    }

    function toast(msg, kind) {
        if (window.bibleReader && typeof window.bibleReader.showToast === 'function') {
            window.bibleReader.showToast(msg, kind || 'info');
        } else {
            console.log('[study]', msg);
        }
    }

    function currentReader() { return window.bibleReader || null; }

    // Lightweight inline confirmation modal — friendlier than window.confirm.
    function confirmInline(message) {
        return new Promise((resolve) => {
            const wrap = document.createElement('div');
            wrap.className = 'study-confirm';
            wrap.innerHTML = `
              <div class="study-confirm-card" role="alertdialog" aria-modal="true">
                <p class="study-confirm-msg"></p>
                <div class="study-confirm-actions">
                  <button class="study-btn" data-act="no">Cancel</button>
                  <button class="study-btn primary" data-act="yes">Yes, delete</button>
                </div>
              </div>`;
            wrap.querySelector('.study-confirm-msg').textContent = message;
            document.body.appendChild(wrap);
            const close = (val) => { wrap.remove(); resolve(val); };
            wrap.addEventListener('click', (e) => {
                if (e.target === wrap) close(false);
                if (e.target.dataset && e.target.dataset.act === 'yes') close(true);
                if (e.target.dataset && e.target.dataset.act === 'no') close(false);
            });
            document.addEventListener('keydown', function onKey(e) {
                if (e.key === 'Escape') { document.removeEventListener('keydown', onKey); close(false); }
                if (e.key === 'Enter')  { document.removeEventListener('keydown', onKey); close(true); }
            });
            setTimeout(() => wrap.querySelector('[data-act=yes]').focus(), 30);
        });
    }

    // Read currently-displayed reference from the BibleReader if available.
    function currentRef() {
        const br = currentReader();
        if (!br) return { book: 'John', chapter: 1, verse: 1, translation: 'NIV' };
        return {
            book: br.currentBook || 'John',
            chapter: br.currentChapter || 1,
            verse: br.currentVerse || 1,
            translation: br.currentTranslation || br.currentTranslation2 || 'NIV',
        };
    }

    // ---- root UI --------------------------------------------------------
    function injectShell() {
        if ($('#study-overlay')) return;

        // Wire up the existing Study tools button in the audio control bar
        // (templates/index.html). We no longer create a separate floating
        // FAB — the play-bar button is the single entry point.
        const trigger = $('#studyToolsBtn');
        if (trigger && !trigger.dataset.studyWired) {
            trigger.dataset.studyWired = '1';
            trigger.addEventListener('click', (e) => { e.preventDefault(); openPanel(); });
        }

        const overlay = document.createElement('div');
        overlay.id = 'study-overlay';
        overlay.className = 'study-overlay';
        overlay.setAttribute('hidden', '');
        overlay.innerHTML = html`
          <div class="study-modal" role="dialog" aria-modal="true" aria-labelledby="study-title">
            <header class="study-head">
              <h2 id="study-title">Study tools</h2>
              <div class="study-tabs" role="tablist">
                ${tabBtn('home', 'Home')}
                ${tabBtn('search', 'Search')}
                ${tabBtn('concordance', 'Compare words')}
                ${tabBtn('xrefs', 'Related verses')}
                ${tabBtn('lemma', 'Hebrew helper')}
                ${tabBtn('tags', 'My tags')}
                ${tabBtn('outlines', 'Sermons')}
                ${tabBtn('playlists', 'Verse lists')}
                ${tabBtn('plans', 'Reading plan')}
                ${tabBtn('notebooks', 'Group notes')}
                ${tabBtn('share', 'Share & export')}
                ${tabBtn('settings', 'Settings')}
              </div>
              <button class="study-close" aria-label="Close" title="Close (Esc)">×</button>
            </header>
            <div class="study-body" id="study-body"></div>
          </div>`;
        document.body.appendChild(overlay);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closePanel();
        });
        $('.study-close', overlay).addEventListener('click', closePanel);
        $$('.study-tab', overlay).forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.tab)));

        // Keyboard shortcuts cheat-sheet overlay.
        const keys = document.createElement('div');
        keys.id = 'study-keys';
        keys.className = 'study-keys';
        keys.setAttribute('hidden', '');
        keys.innerHTML = html`
          <div class="study-keys-card">
            <h3>Keyboard shortcuts</h3>
            <ul>
              <li><kbd>S</kbd> Open study tools</li>
              <li><kbd>J</kbd> / <kbd>K</kbd> Next / previous verse</li>
              <li><kbd>N</kbd> / <kbd>P</kbd> Next / previous chapter</li>
              <li><kbd>G</kbd> Jump to reference</li>
              <li><kbd>F</kbd> Search this translation</li>
              <li><kbd>D</kbd> Toggle dyslexia mode</li>
              <li><kbd>Space</kbd> Play / pause audio</li>
              <li><kbd>?</kbd> Toggle this help</li>
              <li><kbd>Esc</kbd> Close panels</li>
            </ul>
            <button class="study-btn">Close</button>
          </div>`;
        document.body.appendChild(keys);
        keys.addEventListener('click', (e) => {
            if (e.target === keys || e.target.classList.contains('study-btn')) keys.setAttribute('hidden', '');
        });

        // Footnotes drawer.
        const fn = document.createElement('aside');
        fn.id = 'footnotes-drawer';
        fn.className = 'footnotes-drawer';
        fn.setAttribute('hidden', '');
        fn.innerHTML = '<header><h3>Footnotes</h3><button class="study-btn" data-act="close">×</button></header><div class="footnotes-body"></div>';
        document.body.appendChild(fn);
        $('button[data-act=close]', fn).addEventListener('click', () => fn.setAttribute('hidden', ''));
    }

    function tabBtn(id, label) {
        return `<button class="study-tab" role="tab" data-tab="${id}">${esc(label)}</button>`;
    }

    function openPanel(initialTab) {
        injectShell();
        const o = $('#study-overlay');
        o.removeAttribute('hidden');
        document.body.classList.add('study-open');
        switchTab(initialTab || state.lastTab || 'home');
    }
    function closePanel() {
        const o = $('#study-overlay');
        if (o) o.setAttribute('hidden', '');
        document.body.classList.remove('study-open');
    }

    const state = { lastTab: 'home' };

    function switchTab(name) {
        state.lastTab = name;
        $$('#study-overlay .study-tab').forEach((b) =>
            b.classList.toggle('active', b.dataset.tab === name));
        const body = $('#study-body');
        if (!body) return;
        body.innerHTML = '<p class="study-loading">Loading…</p>';
        (TABS[name] || TABS.home)(body).catch((e) => {
            body.innerHTML = `<p class="study-error">${esc(e.message || e)}</p>`;
        });
        updatePermalink();
    }

    // ---- TAB: Home (friendly menu) -------------------------------------
    const TABS = {};

    const SVG_NS = 'http://www.w3.org/2000/svg';
    function ic(path, opts) {
        const a = (opts && opts.attrs) || '';
        return `<svg xmlns="${SVG_NS}" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${a}>${path}</svg>`;
    }
    const ICONS = {
        search:      ic('<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'),
        compare:     ic('<line x1="4" y1="20" x2="4" y2="10"/><line x1="10" y1="20" x2="10" y2="4"/><line x1="16" y1="20" x2="16" y2="14"/><line x1="22" y1="20" x2="22" y2="8"/><line x1="2" y1="20" x2="24" y2="20"/>'),
        xrefs:       ic('<path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5"/>'),
        hebrew:      ic('<polygon points="12 2 15 8 22 9 17 14 18 21 12 18 6 21 7 14 2 9 9 8 12 2"/>'),
        tags:        ic('<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>'),
        outlines:    ic('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>'),
        playlist:    ic('<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'),
        plan:        ic('<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>'),
        notebooks:   ic('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
        share:       ic('<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/>'),
        settings:    ic('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.36.13.7.32 1 .56V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    };

    const HOME_CARDS = [
        { tab: 'search',      icon: ICONS.search,    title: 'Search the Bible',
          desc: 'Find any word or phrase across translations.' },
        { tab: 'concordance', icon: ICONS.compare,   title: 'Compare a word',
          desc: 'See how often a word appears in NIV, KJV, ESV, Hebrew, and more.' },
        { tab: 'xrefs',       icon: ICONS.xrefs,     title: 'Related verses',
          desc: 'Find cross-references for the verse you\u2019re reading.' },
        { tab: 'lemma',       icon: ICONS.hebrew,    title: 'Hebrew helper',
          desc: 'Look up a Hebrew word and bridge it to English translations.' },
        { tab: 'tags',        icon: ICONS.tags,      title: 'My tags',
          desc: 'Color-code verses by topic and revisit them later.' },
        { tab: 'outlines',    icon: ICONS.outlines,  title: 'Sermon outlines',
          desc: 'Build outlines with notes, scripture, and a print handout.' },
        { tab: 'playlists',   icon: ICONS.playlist,  title: 'Verse lists',
          desc: 'Collect verses for preaching and present them full-screen.' },
        { tab: 'plans',       icon: ICONS.plan,      title: 'Reading plan',
          desc: 'Pick a daily plan and tick off each day as you go.' },
        { tab: 'notebooks',   icon: ICONS.notebooks, title: 'Group notes',
          desc: 'Share a notebook with friends or a small group.' },
        { tab: 'share',       icon: ICONS.share,     title: 'Share & export',
          desc: 'Save a verse image, copy a permalink, or export everything.' },
        { tab: 'settings',    icon: ICONS.settings,  title: 'Settings',
          desc: 'Dyslexia mode, text size, interlinear, and more.' },
    ];

    TABS.home = async function (root) {
        const ref = currentRef();
        root.innerHTML = html`
          <p class="study-hint">
            Pick a tool below. The current verse
            (<strong>${esc(ref.book)} ${ref.chapter}:${ref.verse}</strong>) is filled in for you wherever it makes sense.
            Press <kbd>?</kbd> any time to see keyboard shortcuts.
          </p>
          <div class="study-home-grid">
            ${HOME_CARDS.map(c => `
              <button class="study-home-card" data-go="${c.tab}">
                <span class="study-home-icon" aria-hidden="true">${c.icon}</span>
                <span class="study-home-title">${esc(c.title)}</span>
                <span class="study-home-desc">${esc(c.desc)}</span>
              </button>`).join('')}
          </div>`;
        $$('.study-home-card', root).forEach(c => c.addEventListener('click', () => switchTab(c.dataset.go)));
    };

    // ---- TAB: Compare words (concordance) ------------------------------

    TABS.concordance = async function (root) {
        root.innerHTML = html`
          <h3>Compare a word across translations</h3>
          <p class="study-hint">Type one word to see how many times each translation uses it. Hold Ctrl/⌘ to pick more than one translation.</p>
          <div class="study-form">
            <label>Word
              <input type="text" id="cc-word" placeholder="e.g. love, Jesus, Isten" />
            </label>
            <label>Translations
              <select id="cc-tr" multiple size="6">
                ${['NIV','NKJV','KJV','ESV','NASB1995','Hungarian','Hungarian-Revised','Hebrew','Kenyah']
                  .map(t => `<option value="${t}" ${t==='NIV'||t==='KJV'?'selected':''}>${t}</option>`).join('')}
              </select>
            </label>
            <button class="study-btn primary" id="cc-go">Compare</button>
          </div>
          <div id="cc-out" class="study-out"></div>`;
        const word = currentSelectionWord();
        if (word) $('#cc-word').value = word;
        $('#cc-go').addEventListener('click', runConcordance);
        $('#cc-word').addEventListener('keydown', (e) => { if (e.key === 'Enter') runConcordance(); });
        if (word) runConcordance();
    };

    async function runConcordance() {
        const w = $('#cc-word').value.trim();
        if (!w) return;
        const sel = $$('#cc-tr option').filter(o => o.selected).map(o => o.value);
        const url = `/api/words/concordance?word=${encodeURIComponent(w)}&translations=${encodeURIComponent(sel.join(',') || 'ALL')}`;
        const out = $('#cc-out');
        out.innerHTML = '<p class="study-loading">Counting…</p>';
        try {
            const r = await api(url);
            const rows = Object.entries(r.breakdown).sort((a,b)=>b[1].count-a[1].count);
            const max = Math.max(1, ...rows.map(([,v]) => v.count));
            out.innerHTML = html`
              <h3>“${esc(r.word)}” across translations</h3>
              <table class="study-bars">
                <thead><tr><th>Translation</th><th>Hits</th><th>Verses</th><th></th></tr></thead>
                <tbody>${rows.map(([t,v]) => `
                  <tr>
                    <td>${esc(t)}</td><td>${v.count}</td><td>${v.verses}</td>
                    <td><span class="bar" style="width:${Math.round(v.count/max*100)}%"></span></td>
                  </tr>`).join('')}
                </tbody>
              </table>`;
        } catch (e) { out.innerHTML = `<p class="study-error">${esc(e.message)}</p>`; }
    }

    // ---- TAB: Search ----------------------------------------------------
    TABS.search = async function (root) {
        root.innerHTML = html`
          <h3>Search the Bible</h3>
          <p class="study-hint">Type any word or phrase. Use quotes for exact matches — e.g. <code>"in the beginning"</code>. Add <code>book:John</code> to limit by book.</p>
          <div class="study-form">
            <label>Search for
              <input type="text" id="sr-q" placeholder='"in the beginning" book:John' />
            </label>
            <label>Translation
              <select id="sr-tr">
                ${['NIV','NKJV','KJV','ESV','NASB1995','Hungarian','Hungarian-Revised','Hebrew','Kenyah']
                  .map(t => `<option ${t==='NIV'?'selected':''}>${t}</option>`).join('')}
              </select>
            </label>
            <label>Show up to
              <input type="number" id="sr-lim" value="50" min="1" max="500" />
            </label>
            <button class="study-btn primary" id="sr-go">Search</button>
          </div>
          <div id="sr-out" class="study-out"></div>`;
        $('#sr-go').addEventListener('click', runSearch);
        $('#sr-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(); });
    };

    async function runSearch() {
        const q = $('#sr-q').value.trim();
        if (!q) return;
        const tr = $('#sr-tr').value;
        const lim = $('#sr-lim').value || 50;
        const out = $('#sr-out');
        out.innerHTML = '<p class="study-loading">Searching…</p>';
        try {
            const r = await api(`/api/words/search?q=${encodeURIComponent(q)}&translation=${encodeURIComponent(tr)}&limit=${lim}`);
            out.innerHTML = html`
              <p class="study-meta">${r.count} matches${r.truncated?' (truncated)':''}</p>
              <ul class="study-hits">
                ${r.results.map(h => `
                  <li>
                    <a href="#" class="study-jump"
                       data-book="${esc(h.book)}" data-ch="${h.chapter}" data-v="${h.verse}">
                       ${esc(h.book)} ${h.chapter}:${h.verse}</a>
                    <span class="snip">${esc(h.snippet)}</span>
                  </li>`).join('')}
              </ul>`;
            wireJumps(out);
        } catch (e) { out.innerHTML = `<p class="study-error">${esc(e.message)}</p>`; }
    }

    function wireJumps(scope) {
        $$('.study-jump', scope).forEach(a => a.addEventListener('click', (e) => {
            e.preventDefault();
            const br = currentReader();
            const book = a.dataset.book, ch = +a.dataset.ch, v = +a.dataset.v;
            if (br && typeof br.changeBook === 'function') {
                try { br.changeBook(book); } catch (_) {}
            }
            if (br && typeof br.changeChapter === 'function') {
                try { br.changeChapter(ch); } catch (_) {}
            }
            closePanel();
            setTimeout(() => {
                const target = document.querySelector(`[data-verse="${v}"]`);
                if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 400);
        }));
    }

    // ---- TAB: Cross-refs -----------------------------------------------
    TABS.xrefs = async function (root) {
        const ref = currentRef();
        root.innerHTML = html`
          <h3>Related verses</h3>
          <p class="study-hint">See cross-references for any verse. The verse you’re reading is filled in — click <em>Use current verse</em> to refresh it.</p>
          <div class="study-form">
            <label>Verse
              <input type="text" id="xr-ref" value="${esc(ref.book)} ${ref.chapter}:${ref.verse}" />
            </label>
            <button class="study-btn" id="xr-here">Use current verse</button>
            <button class="study-btn primary" id="xr-go">Look up</button>
          </div>
          <div id="xr-out" class="study-out"></div>`;
        $('#xr-go').addEventListener('click', runXrefs);
        $('#xr-here').addEventListener('click', () => {
            const r = currentRef();
            $('#xr-ref').value = `${r.book} ${r.chapter}:${r.verse}`;
            runXrefs();
        });
        $('#xr-ref').addEventListener('keydown', (e) => { if (e.key==='Enter') runXrefs(); });
        runXrefs();
    };
    async function runXrefs() {
        const m = ($('#xr-ref').value || '').match(/^(.+?)\s+(\d+):(\d+)$/);
        const out = $('#xr-out');
        if (!m) { out.innerHTML = '<p class="study-error">Use format “Book chapter:verse”</p>'; return; }
        try {
            const r = await api(`/api/crossrefs/${encodeURIComponent(m[1])}/${m[2]}/${m[3]}`);
            if (!r.crossrefs.length) {
                out.innerHTML = '<p class="study-meta">No curated cross-references for this verse yet.</p>';
                return;
            }
            out.innerHTML = `<h3>Cross-references for ${esc(r.ref)}</h3><ul class="study-xrefs">${
                r.crossrefs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
        } catch (e) { out.innerHTML = `<p class="study-error">${esc(e.message)}</p>`; }
    }

    // ---- TAB: Lemma bridge ---------------------------------------------
    TABS.lemma = async function (root) {
        const sel = currentSelectionWord();
        root.innerHTML = html`
          <h3>Hebrew helper</h3>
          <p class="study-hint">Paste or type a Hebrew word, or highlight one in the Hebrew column before opening this tool. <em>Bridge</em> shows English equivalents; <em>Find variants</em> searches every related form in the Hebrew Bible.</p>
          <div class="study-form">
            <label>Hebrew word
              <input type="text" id="lm-word" dir="rtl" placeholder="בְּרֵאשִׁית" value="${esc(sel||'')}" />
            </label>
            <button class="study-btn primary" id="lm-go">Bridge to English</button>
            <button class="study-btn" id="lm-search">Find variants</button>
          </div>
          <div id="lm-out" class="study-out"></div>`;
        $('#lm-go').addEventListener('click', runLemmaBridge);
        $('#lm-search').addEventListener('click', runLemmaSearch);
        $('#lm-word').addEventListener('keydown', (e) => { if (e.key === 'Enter') runLemmaBridge(); });
    };
    async function runLemmaBridge() {
        const w = $('#lm-word').value.trim();
        if (!w) return;
        const out = $('#lm-out');
        out.innerHTML = '<p class="study-loading">Looking up…</p>';
        try {
            const r = await api(`/api/hebrew/lemma-bridge?word=${encodeURIComponent(w)}`);
            if (!r.gloss) { out.innerHTML = '<p class="study-meta">Not in dictionary.</p>'; return; }
            out.innerHTML = html`
              <p><strong dir="rtl">${esc(r.matched)}</strong> — <em>${esc(r.gloss)}</em></p>
              <p class="study-meta">Look this up in English translations:</p>
              <div class="study-chips">${r.candidates.map(c => `<button class="study-chip" data-w="${esc(c)}">${esc(c)}</button>`).join('')}</div>`;
            $$('.study-chip', out).forEach(b => b.addEventListener('click', () => {
                switchTab('concordance');
                setTimeout(() => { const el = $('#cc-word'); if (el) { el.value = b.dataset.w; runConcordance(); } }, 30);
            }));
        } catch (e) { out.innerHTML = `<p class="study-error">${esc(e.message)}</p>`; }
    }
    async function runLemmaSearch() {
        const w = $('#lm-word').value.trim();
        if (!w) return;
        const out = $('#lm-out');
        out.innerHTML = '<p class="study-loading">Searching Hebrew corpus…</p>';
        try {
            const r = await api(`/api/hebrew/lemma-search?word=${encodeURIComponent(w)}&limit=20`);
            out.innerHTML = html`
              <p class="study-meta">${r.count} hits in ${r.verses_with_matches} verses (roots tried: ${r.roots.length})</p>
              <ul class="study-hits">${r.samples.map(s => `
                <li>
                  <a href="#" class="study-jump" data-book="${esc(s.book)}" data-ch="${s.chapter}" data-v="${s.verse}">
                    ${esc(s.book)} ${s.chapter}:${s.verse}</a>
                  <span class="snip" dir="rtl">${esc(s.text)}</span>
                </li>`).join('')}</ul>`;
            wireJumps(out);
        } catch (e) { out.innerHTML = `<p class="study-error">${esc(e.message)}</p>`; }
    }

    // ---- TAB: Tags ------------------------------------------------------
    TABS.tags = async function (root) {
        const r = await api('/api/me/tags');
        const ref = currentRef();
        root.innerHTML = html`
          <h3>My tags</h3>
          <p class="study-hint">Create color-coded tags for topics like <em>Grace</em> or <em>Prayer</em>, then attach the verse you’re reading with one click.</p>
          <div class="study-form">
            <label>New tag name <input type="text" id="tg-name" maxlength="48" placeholder="e.g. Grace"/></label>
            <label>Color <input type="color" id="tg-color" value="#c9a962" /></label>
            <button class="study-btn primary" id="tg-add">Add tag</button>
          </div>
          <ul class="study-list" id="tg-list">
            ${r.tags.map(t => `
              <li>
                <span class="tag-dot" style="background:${esc(t.color||'#c9a962')}"></span>
                <strong>${esc(t.name)}</strong>
                <span class="study-meta">${t.verse_count} verse${t.verse_count===1?'':'s'}</span>
                <button class="study-btn" data-act="view" data-id="${t.id}">View verses</button>
                <button class="study-btn" data-act="del" data-id="${t.id}" data-name="${esc(t.name)}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No tags yet — add one above to get started.</li>'}
          </ul>
          ${r.tags.length ? html`
          <div class="study-form" style="margin-top:1em;">
            <label>Tag <strong>${esc(ref.book)} ${ref.chapter}:${ref.verse}</strong> with
              <select id="tg-pick">${r.tags.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('')}</select>
            </label>
            <button class="study-btn primary" id="tg-link">Tag this verse</button>
          </div>` : ''}
          <div id="tg-out" class="study-out"></div>`;
        $('#tg-add').addEventListener('click', async () => {
            const name = $('#tg-name').value.trim();
            const color = $('#tg-color').value;
            if (!name) { toast('Type a tag name first'); return; }
            await api('/api/me/tags', { method: 'POST', body: { name, color } });
            switchTab('tags');
        });
        $('#tg-name') && $('#tg-name').addEventListener('keydown', (e) => { if (e.key==='Enter') $('#tg-add').click(); });
        if ($('#tg-link')) $('#tg-link').addEventListener('click', async () => {
            const id = +$('#tg-pick').value;
            if (!id) return;
            const c = currentRef();
            await api('/api/me/tag-link', { method: 'POST', body: { tag_id: id, book: c.book, chapter: c.chapter, verse: c.verse } });
            toast('Tagged ✓');
        });
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!await confirmInline(`Delete tag “${b.dataset.name}”? This won’t delete the verses.`)) return;
            await api('/api/me/tags/' + b.dataset.id, { method: 'DELETE' });
            switchTab('tags');
        }));
        $$('button[data-act=view]', root).forEach(b => b.addEventListener('click', async () => {
            const v = await api('/api/me/tags/' + b.dataset.id + '/verses');
            $('#tg-out').innerHTML = v.verses.length
                ? '<h3>Tagged verses</h3><ul class="study-hits">' + v.verses.map(x =>
                    `<li><a href="#" class="study-jump" data-book="${esc(x.book)}" data-ch="${x.chapter}" data-v="${x.verse}">${esc(x.book)} ${x.chapter}:${x.verse}</a></li>`
                ).join('') + '</ul>'
                : '<p class="study-meta">No verses tagged yet. Use the form above to attach this verse.</p>';
            wireJumps($('#tg-out'));
        }));
    };

    // ---- TAB: Outlines --------------------------------------------------
    TABS.outlines = async function (root) {
        const r = await api('/api/me/outlines');
        root.innerHTML = html`
          <h3>Sermon outlines</h3>
          <p class="study-hint">Plan a sermon: title, theme, free-form notes, and a list of verses. Hit <em>Print handout</em> to get a clean printable copy.</p>
          <div class="study-form">
            <label>New outline title <input type="text" id="ol-new-title" placeholder="e.g. The Good Shepherd" /></label>
            <button class="study-btn primary" id="ol-new">Create</button>
          </div>
          <ul class="study-list" id="ol-list">
            ${r.outlines.map(o => `
              <li>
                <strong>${esc(o.title)}</strong>
                <span class="study-meta">updated ${esc((o.updated_at||'').slice(0,10))}</span>
                <button class="study-btn primary" data-act="present" data-id="${o.id}">Present</button>
                <button class="study-btn" data-act="open" data-id="${o.id}">Edit</button>
                <a class="study-btn" href="/api/me/outlines/${o.id}/export?translation=NIV" target="_blank">Print handout</a>
                <button class="study-btn" data-act="del" data-id="${o.id}" data-name="${esc(o.title)}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No outlines yet — type a title above and hit Create.</li>'}
          </ul>
          <div id="ol-edit" class="study-out"></div>`;
        $('#ol-new').addEventListener('click', async () => {
            const t = $('#ol-new-title').value.trim();
            if (!t) { toast('Type a title first'); return; }
            await api('/api/me/outlines', { method: 'POST', body: { title: t } });
            switchTab('outlines');
        });
        $('#ol-new-title').addEventListener('keydown', (e) => { if (e.key==='Enter') $('#ol-new').click(); });
        $$('button[data-act=present]', root).forEach(b => b.addEventListener('click', () => openPresent(+b.dataset.id)));
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!await confirmInline(`Delete outline “${b.dataset.name}”?`)) return;
            await api('/api/me/outlines/' + b.dataset.id, { method: 'DELETE' });
            switchTab('outlines');
        }));
        $$('button[data-act=open]', root).forEach(b => b.addEventListener('click', async () => {
            const o = (await api('/api/me/outlines/' + b.dataset.id)).outline;
            const ed = $('#ol-edit');
            ed.innerHTML = html`
              <h3>Edit outline</h3>
              <p class="study-hint">Write your notes freely. Add verses one at a time using the form below — the current verse is filled in for you.</p>
              <div class="study-form">
                <label>Title <input type="text" id="ol-title" value="${esc(o.title)}"/></label>
                <label>Theme <input type="text" id="ol-theme" value="${esc(o.theme||'')}"/></label>
              </div>
              <label class="study-form" style="flex-direction:column;align-items:stretch;">
                Notes
                <textarea id="ol-body" rows="8" placeholder="Write your sermon notes here…">${esc(o.body_md||'')}</textarea>
              </label>
              <h3 style="margin-top:18px;">Verses</h3>
              <ul class="study-list" id="ol-vlist">
                ${o.verses.map((v,i) => `
                  <li data-i="${i}">
                    <strong>${esc(v.book)} ${v.chapter}:${v.verse}</strong>
                    ${v.label ? `<span class="study-meta">${esc(v.label)}</span>` : ''}
                    <button class="study-btn" data-vrm="${i}">Remove</button>
                  </li>`).join('') || '<li class="study-meta">No verses yet.</li>'}
              </ul>
              <div class="study-form">
                <label>Add verse <input type="text" id="ol-vref" value="${esc(currentRef().book)} ${currentRef().chapter}:${currentRef().verse}" /></label>
                <label>Label (optional) <input type="text" id="ol-vlabel" placeholder="e.g. Main point" /></label>
                <button class="study-btn" id="ol-vhere">Use current verse</button>
                <button class="study-btn primary" id="ol-vadd">Add</button>
              </div>
              <div class="study-form">
                <button class="study-btn primary" id="ol-save">Save outline</button>
                <button class="study-btn" id="ol-present">Present</button>
                <button class="study-btn" id="ol-print">Print handout</button>
              </div>`;
            const verses = o.verses.slice();
            const renderVerses = () => {
                $('#ol-vlist', ed).innerHTML = verses.map((v,i) => `
                    <li data-i="${i}">
                      <strong>${esc(v.book)} ${v.chapter}:${v.verse}</strong>
                      ${v.label ? `<span class="study-meta">${esc(v.label)}</span>` : ''}
                      <button class="study-btn" data-vrm="${i}">Remove</button>
                    </li>`).join('') || '<li class="study-meta">No verses yet.</li>';
                $$('button[data-vrm]', ed).forEach(b => b.addEventListener('click', () => {
                    verses.splice(+b.dataset.vrm, 1); renderVerses();
                }));
            };
            renderVerses();
            $('#ol-vhere').addEventListener('click', () => {
                const r2 = currentRef();
                $('#ol-vref').value = `${r2.book} ${r2.chapter}:${r2.verse}`;
            });
            $('#ol-vadd').addEventListener('click', () => {
                const m = ($('#ol-vref').value || '').match(/^\s*(.+?)\s+(\d+):(\d+)\s*$/);
                if (!m) { toast('Use “Book chapter:verse”, e.g. John 3:16', 'error'); return; }
                verses.push({ book: m[1].trim(), chapter: +m[2], verse: +m[3], label: $('#ol-vlabel').value.trim() });
                $('#ol-vlabel').value = '';
                renderVerses();
            });
            $('#ol-save').addEventListener('click', async () => {
                await api('/api/me/outlines/' + o.id, { method: 'PUT', body: {
                    title: $('#ol-title').value, theme: $('#ol-theme').value,
                    body_md: $('#ol-body').value, verses,
                }});
                toast('Saved ✓');
                switchTab('outlines');
            });
            $('#ol-print').addEventListener('click', () => {
                window.open(`/api/me/outlines/${o.id}/export?translation=NIV`, '_blank');
            });
            $('#ol-present').addEventListener('click', () => openPresent(o.id));
        }));
    };

    // ---- TAB: Sermon list (playlists) -----------------------------------
    TABS.playlists = async function (root) {
        const r = await api('/api/me/playlists');
        const ref = currentRef();
        root.innerHTML = html`
          <h3>Verse lists</h3>
          <p class="study-hint">Collect verses for a sermon, devotional, or memorization. <em>Preach view</em> opens a full-screen, large-text presentation.</p>
          <div class="study-form">
            <label>New list title <input type="text" id="pl-new-title" placeholder="e.g. Easter morning" /></label>
            <button class="study-btn primary" id="pl-new">Create</button>
          </div>
          <ul class="study-list">
            ${r.playlists.map(p => `
              <li>
                <strong>${esc(p.title)}</strong>
                <span class="study-meta">${p.item_count} verse${p.item_count===1?'':'s'}</span>
                <button class="study-btn primary" data-act="preach" data-id="${p.id}">Preach view</button>
                <button class="study-btn" data-act="add" data-id="${p.id}">Add ${esc(ref.book)} ${ref.chapter}:${ref.verse}</button>
                <button class="study-btn" data-act="del" data-id="${p.id}" data-name="${esc(p.title)}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No verse lists yet — type a title above and hit Create.</li>'}
          </ul>`;
        $('#pl-new').addEventListener('click', async () => {
            const t = $('#pl-new-title').value.trim();
            if (!t) { toast('Type a title first'); return; }
            await api('/api/me/playlists', { method: 'POST', body: { title: t } });
            switchTab('playlists');
        });
        $('#pl-new-title').addEventListener('keydown', (e) => { if (e.key==='Enter') $('#pl-new').click(); });
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!await confirmInline(`Delete verse list “${b.dataset.name}”?`)) return;
            await api('/api/me/playlists/' + b.dataset.id, { method: 'DELETE' });
            switchTab('playlists');
        }));
        $$('button[data-act=add]', root).forEach(b => b.addEventListener('click', async () => {
            const c = currentRef();
            await api(`/api/me/playlists/${b.dataset.id}/items`, { method: 'POST', body: { book: c.book, chapter: c.chapter, verse_start: c.verse, verse_end: c.verse } });
            toast('Added ✓');
        }));
        $$('button[data-act=preach]', root).forEach(b => b.addEventListener('click', () => openPreach(+b.dataset.id)));
    };

    // ---- Presentation viewer -------------------------------------------
    // A PowerPoint-style in-page slide deck, themed with the site's tokens.
    // Used for outlines (Sermons tab → Present) and playlists (Preach view).
    //
    // slides = [{ kind: 'title'|'theme'|'note'|'verse'|'end',
    //             eyebrow, title, body, ref, note }]
    function buildOutlineSlides(o, fetched) {
        const slides = [{ kind: 'title', eyebrow: o.theme || 'Sermon', title: o.title }];
        const notes = (o.body_md || '').split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
        notes.forEach(block => {
            // Treat a leading "# Heading" line as a section title.
            const hm = block.match(/^#{1,3}\s+(.+)$/m);
            if (hm && block.trim().split('\n').length === 1) {
                slides.push({ kind: 'note', title: hm[1] });
            } else {
                slides.push({ kind: 'note', body: block });
            }
        });
        (o.verses || []).forEach(v => {
            const key = `${v.book}|${v.chapter}|${v.verse}`;
            slides.push({
                kind: 'verse',
                eyebrow: v.label || '',
                ref: `${v.book} ${v.chapter}:${v.verse}`,
                body: fetched[key] || '',
            });
        });
        slides.push({ kind: 'end', title: 'Amen.' });
        return slides;
    }

    function buildPlaylistSlides(p, items) {
        const slides = [{ kind: 'title', eyebrow: 'Verse list', title: p.title }];
        items.forEach(it => {
            slides.push({
                kind: 'verse',
                eyebrow: it.note || '',
                ref: it.ref,
                body: it.text || '',
            });
        });
        slides.push({ kind: 'end', title: 'Amen.' });
        return slides;
    }

    async function fetchVerseTexts(verseRefs) {
        // verseRefs: [{book, chapter, verse}]; returns { "book|ch|v": text }
        const out = {};
        const chapters = new Map(); // key: book|chapter → Promise
        const tr = (currentRef().translation || 'NIV');
        for (const v of verseRefs) {
            const ck = `${v.book}|${v.chapter}`;
            if (!chapters.has(ck)) {
                chapters.set(ck, api(`/api/parallel/${encodeURIComponent(v.book)}/${v.chapter}/${encodeURIComponent(tr)}/Hebrew`).catch(() => null));
            }
        }
        for (const v of verseRefs) {
            const ch = await chapters.get(`${v.book}|${v.chapter}`);
            const verses = ch && ch.translation1 && ch.translation1.verses;
            const text = verses ? (verses[v.verse] || verses[String(v.verse)] || '') : '';
            out[`${v.book}|${v.chapter}|${v.verse}`] = text;
        }
        return out;
    }

    async function openPresent(outlineId) {
        const o = (await api('/api/me/outlines/' + outlineId)).outline;
        const fetched = await fetchVerseTexts(o.verses || []);
        launchDeck(buildOutlineSlides(o, fetched), o.title);
    }

    async function openPreach(pid) {
        const p = (await api('/api/me/playlists/' + pid)).playlist;
        const tr = (currentRef().translation || 'NIV');
        const items = [];
        for (const item of (p.items || [])) {
            try {
                const ch = await api(`/api/parallel/${encodeURIComponent(item.book)}/${item.chapter}/${encodeURIComponent(tr)}/Hebrew`);
                const start = item.verse_start || 1, end = item.verse_end || start;
                for (let v = start; v <= end; v++) {
                    const text = (ch.translation1 && ch.translation1.verses && (ch.translation1.verses[v] || ch.translation1.verses[String(v)])) || '';
                    if (text) items.push({ ref: `${item.book} ${item.chapter}:${v}`, text, note: item.note });
                }
            } catch (_) {}
        }
        launchDeck(buildPlaylistSlides(p, items), p.title);
    }

    function launchDeck(slides, title) {
        if (!slides.length) { toast('Nothing to present'); return; }
        const deck = document.createElement('div');
        deck.className = 'study-deck';
        deck.setAttribute('role', 'dialog');
        deck.setAttribute('aria-label', 'Presentation: ' + title);
        deck.innerHTML = `
          <div class="deck-stage" id="deck-stage"></div>
          <div class="deck-progress"><div class="deck-progress-fill" id="deck-fill"></div></div>
          <div class="deck-bar">
            <button class="deck-btn" id="deck-prev" title="Previous (←)" aria-label="Previous slide">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <span class="deck-count" id="deck-count">1 / ${slides.length}</span>
            <button class="deck-btn" id="deck-next" title="Next (→ / Space)" aria-label="Next slide">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
            <span class="deck-spacer"></span>
            <button class="deck-btn" id="deck-fs" title="Fullscreen (F)" aria-label="Toggle fullscreen">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>
            </button>
            <button class="deck-btn" id="deck-print" title="Print handout (P)" aria-label="Print handout">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            </button>
            <button class="deck-btn" id="deck-close" title="Close (Esc)" aria-label="Close presentation">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="18" x2="18" y2="6"/></svg>
            </button>
          </div>
          <div class="deck-handout" id="deck-handout" aria-hidden="true"></div>`;
        document.body.appendChild(deck);
        document.body.classList.add('deck-open');

        let idx = 0;
        const stage = $('#deck-stage', deck);
        const fill  = $('#deck-fill', deck);
        const count = $('#deck-count', deck);

        function renderSlide(s, dir) {
            const card = document.createElement('section');
            card.className = 'deck-slide deck-slide--' + s.kind;
            card.dataset.dir = dir || 'in';
            let inner = '';
            if (s.eyebrow) inner += `<div class="deck-eyebrow">${esc(s.eyebrow)}</div>`;
            if (s.kind === 'verse') {
                inner += `<div class="deck-ref">${esc(s.ref || '')}</div>`;
                inner += `<blockquote class="deck-verse">${esc(s.body || '(verse text unavailable)')}</blockquote>`;
            } else if (s.kind === 'title') {
                inner += `<h1 class="deck-title">${esc(s.title || '')}</h1>`;
                inner += `<div class="deck-mark"></div>`;
            } else if (s.kind === 'end') {
                inner += `<h1 class="deck-title deck-end">${esc(s.title || 'Amen.')}</h1>`;
            } else if (s.kind === 'note') {
                if (s.title) inner += `<h2 class="deck-heading">${esc(s.title)}</h2>`;
                if (s.body)  inner += `<div class="deck-body">${esc(s.body).replace(/\n/g, '<br>')}</div>`;
            }
            card.innerHTML = inner;
            return card;
        }

        function show(newIdx, dir) {
            newIdx = Math.max(0, Math.min(slides.length - 1, newIdx));
            if (newIdx === idx && stage.firstChild) return;
            const direction = dir || (newIdx > idx ? 'next' : 'prev');
            const old = stage.firstChild;
            const card = renderSlide(slides[newIdx], direction);
            stage.appendChild(card);
            requestAnimationFrame(() => card.classList.add('is-in'));
            if (old) {
                old.classList.add('is-out-' + direction);
                setTimeout(() => old.remove(), 380);
            }
            idx = newIdx;
            count.textContent = `${idx + 1} / ${slides.length}`;
            fill.style.width = (((idx + 1) / slides.length) * 100).toFixed(2) + '%';
        }

        const next = () => show(idx + 1, 'next');
        const prev = () => show(idx - 1, 'prev');

        $('#deck-next', deck).addEventListener('click', next);
        $('#deck-prev', deck).addEventListener('click', prev);
        $('#deck-close', deck).addEventListener('click', close);
        $('#deck-fs', deck).addEventListener('click', toggleFs);
        $('#deck-print', deck).addEventListener('click', printHandout);

        function onKey(e) {
            if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); next(); }
            else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); prev(); }
            else if (e.key === 'Escape') { close(); }
            else if (e.key === 'Home') { show(0); }
            else if (e.key === 'End')  { show(slides.length - 1); }
            else if (e.key === 'f' || e.key === 'F') { toggleFs(); }
            else if (e.key === 'p' || e.key === 'P') { printHandout(); }
        }
        document.addEventListener('keydown', onKey);

        // Touch swipe
        let touchX = null;
        deck.addEventListener('touchstart', (e) => { touchX = e.touches[0].clientX; }, { passive: true });
        deck.addEventListener('touchend', (e) => {
            if (touchX == null) return;
            const dx = e.changedTouches[0].clientX - touchX;
            if (Math.abs(dx) > 50) (dx < 0 ? next : prev)();
            touchX = null;
        }, { passive: true });

        function toggleFs() {
            if (!document.fullscreenElement) {
                (deck.requestFullscreen || deck.webkitRequestFullscreen || (() => {})).call(deck);
            } else {
                (document.exitFullscreen || document.webkitExitFullscreen || (() => {})).call(document);
            }
        }

        function printHandout() {
            const h = $('#deck-handout', deck);
            h.innerHTML = `<h1>${esc(title)}</h1>` + slides.map(s => {
                if (s.kind === 'title' || s.kind === 'end') return `<section class="ph"><h2>${esc(s.title || '')}</h2>${s.eyebrow?`<p class="phe">${esc(s.eyebrow)}</p>`:''}</section>`;
                if (s.kind === 'verse') return `<section class="ph"><h3>${esc(s.ref || '')}</h3>${s.eyebrow?`<p class="phe">${esc(s.eyebrow)}</p>`:''}<blockquote>${esc(s.body || '')}</blockquote></section>`;
                return `<section class="ph">${s.title?`<h3>${esc(s.title)}</h3>`:''}${s.body?`<p>${esc(s.body).replace(/\n/g,'<br>')}</p>`:''}</section>`;
            }).join('');
            window.print();
        }

        function close() {
            document.removeEventListener('keydown', onKey);
            if (document.fullscreenElement) { try { document.exitFullscreen(); } catch (_) {} }
            deck.remove();
            document.body.classList.remove('deck-open');
        }

        show(0, 'in');
    }

    // ---- TAB: Reading plan ----------------------------------------------
    TABS.plans = async function (root) {
        const list = await api('/api/plans');
        root.innerHTML = html`
          <div class="study-form">
            <label>Plan
              <select id="pn-pick">${list.plans.map(p => `<option value="${p.slug}">${esc(p.title)}</option>`).join('')}</select>
            </label>
            <button class="study-btn primary" id="pn-go">Open</button>
          </div>
          <div id="pn-out" class="study-out"></div>`;
        $('#pn-go').addEventListener('click', () => loadPlan($('#pn-pick').value));
        loadPlan(list.plans[0].slug);
    };
    async function loadPlan(slug) {
        const out = $('#pn-out');
        out.innerHTML = '<p class="study-loading">Loading…</p>';
        const [plan, prog] = await Promise.all([
            api('/api/plans/' + slug),
            api('/api/me/plans/' + slug + '/progress').catch(() => ({ completed_days: [] })),
        ]);
        const done = new Set(prog.completed_days);
        out.innerHTML = html`
          <h3>${esc(plan.title)}</h3>
          <p class="study-meta">${esc(plan.summary)} — ${plan.days.length} days, ${done.size} completed</p>
          <ol class="plan-days">
            ${plan.days.map((refs, i) => `
              <li class="${done.has(i+1)?'done':''}">
                <label>
                  <input type="checkbox" data-day="${i+1}" ${done.has(i+1)?'checked':''}/>
                  Day ${i+1}: ${refs.slice(0,4).map(r => esc(r)).join(', ')}${refs.length>4?` (+${refs.length-4} more)`:''}
                </label>
              </li>`).join('')}
          </ol>`;
        $$('input[data-day]', out).forEach(cb => cb.addEventListener('change', async () => {
            await api('/api/me/plans/' + slug + '/progress', {
                method: 'POST', body: { day: +cb.dataset.day, completed: cb.checked },
            });
            cb.parentElement.parentElement.classList.toggle('done', cb.checked);
        }));
    }

    // ---- TAB: Notebooks (shared) ----------------------------------------
    TABS.notebooks = async function (root) {
        const r = await api('/api/me/notebooks');
        if (r.needs_login) {
            root.innerHTML = '<h3>Group notes</h3><p class="study-hint">Sign in (top-right) to create or join a shared notebook with your study group.</p>';
            return;
        }
        root.innerHTML = html`
          <h3>Group notes</h3>
          <p class="study-hint">Share a notebook with friends. Each member can post a note tied to a verse, and everyone sees the same thread.</p>
          <div class="study-form">
            <label>New notebook title <input type="text" id="nb-new-title" placeholder="e.g. Wednesday study group" /></label>
            <button class="study-btn primary" id="nb-new">Create</button>
          </div>
          <div class="study-form">
            <label>Join with code <input type="text" id="nb-token" placeholder="Paste invite code…" /></label>
            <button class="study-btn" id="nb-join">Join</button>
          </div>
          <ul class="study-list">
            ${r.notebooks.map(n => `
              <li>
                <strong>${esc(n.title)}</strong>
                <span class="study-meta">${n.member_count} member${n.member_count===1?'':'s'}${n.is_owner?' • owner':''}</span>
                ${n.is_owner ? `<button class="study-btn" data-act="share" data-tok="${esc(n.share_token)}">Copy invite link</button>` : ''}
                <button class="study-btn primary" data-act="open" data-id="${n.id}">Open</button>
              </li>`).join('') || '<li class="study-meta">No notebooks yet — create one above to share with your group.</li>'}
          </ul>
          <div id="nb-out" class="study-out"></div>`;
        $('#nb-new').addEventListener('click', async () => {
            const t = $('#nb-new-title').value.trim();
            if (!t) { toast('Type a title first'); return; }
            await api('/api/me/notebooks', { method: 'POST', body: { title: t } });
            switchTab('notebooks');
        });
        $('#nb-new-title').addEventListener('keydown', (e) => { if (e.key==='Enter') $('#nb-new').click(); });
        $('#nb-join').addEventListener('click', async () => {
            const tok = $('#nb-token').value.trim();
            if (!tok) return;
            await api('/api/notebooks/join/' + encodeURIComponent(tok), { method: 'POST' });
            switchTab('notebooks');
        });
        $$('button[data-act=share]', root).forEach(b => b.addEventListener('click', () => {
            const url = location.origin + location.pathname + '#join=' + b.dataset.tok;
            navigator.clipboard.writeText(url).then(() => toast('Invite link copied ✓'));
        }));
        $$('button[data-act=open]', root).forEach(b => b.addEventListener('click', async () => {
            const d = await api('/api/me/notebooks/' + b.dataset.id);
            const ref = currentRef();
            $('#nb-out').innerHTML = html`
              <h3>${esc(d.notebook.title)}</h3>
              <label class="study-form" style="flex-direction:column;align-items:stretch;">
                Add a note for <strong>${esc(ref.book)} ${ref.chapter}:${ref.verse}</strong>
                <textarea id="nb-body" rows="3" placeholder="What stood out to you?…"></textarea>
              </label>
              <button class="study-btn primary" id="nb-add">Post</button>
              <ul class="study-list" style="margin-top:14px;">${d.entries.length ? d.entries.map(e => `
                <li>
                  <strong>${esc(e.author_email||'anon')}</strong>
                  ${e.book?`<span class="study-meta">${esc(e.book)} ${e.chapter}:${e.verse}</span>`:''}
                  <p style="flex-basis:100%;margin:6px 0 0;">${esc(e.body_md)}</p>
                  <span class="study-meta">${esc((e.created_at||'').replace('T',' ').slice(0,16))}</span>
                </li>`).join('') : '<li class="study-meta">No notes yet — be the first.</li>'}</ul>`;
            $('#nb-add').addEventListener('click', async () => {
                const body = $('#nb-body').value.trim();
                if (!body) { toast('Type something first'); return; }
                const r2 = currentRef();
                await api('/api/me/notebooks/' + b.dataset.id + '/entries', { method: 'POST', body: {
                    body_md: body, book: r2.book, chapter: r2.chapter, verse: r2.verse,
                }});
                toast('Posted ✓');
                $$('button[data-act=open]', root).find(x => x.dataset.id === b.dataset.id).click();
            });
        }));
    };

    // ---- TAB: Share / export -------------------------------------------
    TABS.share = async function (root) {
        const ref = currentRef();
        root.innerHTML = html`
          <h3>Share &amp; export</h3>
          <p class="study-hint">Quick exports for the chapter you're reading, plus full backups of everything you've saved.</p>

          <h3>Current chapter</h3>
          <p class="study-meta">${esc(ref.book)} ${ref.chapter} (${esc(ref.translation)})</p>
          <div class="study-form">
            <button class="study-btn primary" id="sh-md">Export chapter as Markdown</button>
            <button class="study-btn" id="sh-copy">Copy chapter text</button>
          </div>

          <h3>Share current verse</h3>
          <p class="study-meta">${esc(ref.book)} ${ref.chapter}:${ref.verse}</p>
          <div class="study-form">
            <button class="study-btn primary" id="sh-png">Download share image (PNG)</button>
            <button class="study-btn" id="sh-link">Copy permalink</button>
          </div>

          <h3>Notes &amp; bookmarks</h3>
          <p class="study-hint">Export everything you've saved while studying.</p>
          <div class="study-form">
            <a class="study-btn primary" href="/api/me/export/notes">Export all my notes</a>
            <a class="study-btn" href="/api/me/export/bookmarks">Export bookmarks</a>
          </div>

          <h3>Full backup</h3>
          <p class="study-meta">A ZIP of your notes, bookmarks, highlights, tags, outlines, sermon lists, plan progress and settings.</p>
          <a class="study-btn primary" href="/api/me/export/all" download>Download .zip</a>`;

        $('#sh-md').addEventListener('click', () => {
            const url = `/api/me/export/chapter/${encodeURIComponent(ref.book)}/${ref.chapter}?translation=${encodeURIComponent(ref.translation)}`;
            window.location.href = url;
        });
        $('#sh-copy').addEventListener('click', async () => {
            try {
                const data = await api(`/api/verses/${encodeURIComponent(ref.book)}/${ref.chapter}?translation=${encodeURIComponent(ref.translation)}`);
                const verses = data.verses || data;
                const lines = [`${ref.book} ${ref.chapter} (${data.translation || ref.translation})`, ''];
                for (const k of Object.keys(verses).map(Number).sort((a, b) => a - b)) {
                    lines.push(`${k}. ${verses[k]}`);
                }
                await navigator.clipboard.writeText(lines.join('\n'));
                toast('Chapter copied to clipboard');
            } catch (_) {
                toast('Copy failed', 'error');
            }
        });
        $('#sh-png').addEventListener('click', async () => {
            const text = grabCurrentVerseText() || (ref.book + ' ' + ref.chapter + ':' + ref.verse);
            const r = `${ref.book} ${ref.chapter}:${ref.verse}`;
            window.open(`/api/share/verse.png?text=${encodeURIComponent(text)}&ref=${encodeURIComponent(r)}`, '_blank');
        });
        $('#sh-link').addEventListener('click', () => {
            updatePermalink();
            navigator.clipboard.writeText(location.href).then(() => toast('Permalink copied'));
        });
    };

    function grabCurrentVerseText() {
        const ref = currentRef();
        const sel = document.querySelector(`[data-verse="${ref.verse}"] .verse-text, [data-verse="${ref.verse}"]`);
        return sel ? (sel.textContent || '').trim().slice(0, 480) : '';
    }

    // ---- TAB: Settings --------------------------------------------------
    TABS.settings = async function (root) {
        const r = await api('/api/me/settings').catch(() => ({ settings: {} }));
        const s = r.settings || {};
        root.innerHTML = html`
          <h3>Display</h3>
          <label class="study-check">
            <input type="checkbox" id="st-dys" ${s.dyslexia==='1'?'checked':''}/> Dyslexia-friendly font &amp; spacing
          </label>
          <label class="study-check">
            <input type="checkbox" id="st-interlin" ${s.interlinear==='1'?'checked':''}/> Inline interlinear (Hebrew → English gloss)
          </label>
          <label class="study-check">
            <input type="checkbox" id="st-large" ${s.largeText==='1'?'checked':''}/> Larger text
          </label>
          <h3>Reading aloud</h3>
          <p class="study-meta">Press <kbd>Space</kbd> to play/pause. Use the audio bar for voice/speed.</p>
          <h3>Cross-translation</h3>
          <button class="study-btn" id="st-greek">Check Greek NT availability</button>
          <p class="study-meta" id="st-greek-out"></p>
          <h3>Reset</h3>
          <button class="study-btn" id="st-clear-tts">Clear local TTS player cache</button>`;
        $('#st-dys').addEventListener('change', async (e) => {
            document.body.classList.toggle('dyslexia', e.target.checked);
            await api('/api/me/settings', { method: 'POST', body: { dyslexia: e.target.checked ? '1' : '0' } });
        });
        $('#st-interlin').addEventListener('change', async (e) => {
            document.body.classList.toggle('interlinear-on', e.target.checked);
            await api('/api/me/settings', { method: 'POST', body: { interlinear: e.target.checked ? '1' : '0' } });
            applyInterlinear(e.target.checked);
        });
        $('#st-large').addEventListener('change', async (e) => {
            document.body.classList.toggle('study-large-text', e.target.checked);
            await api('/api/me/settings', { method: 'POST', body: { largeText: e.target.checked ? '1' : '0' } });
        });
        $('#st-greek').addEventListener('click', async () => {
            const r2 = await api('/api/corpus/availability');
            $('#st-greek-out').textContent = r2.available.sblgnt
                ? 'SBL Greek NT is installed.'
                : 'Greek NT not installed yet — drop the corpus into static/data/bible/sblgnt/ to enable.';
        });
        $('#st-clear-tts').addEventListener('click', () => {
            try { caches.delete('ritd-tts-v1'); } catch (_) {}
            toast('Cleared');
        });
    };

    // ---- Permalink -----------------------------------------------------
    // We only encode the current Bible reference in the URL hash. We do NOT
    // encode the active study tab, so reloading the page never re-opens
    // the study panel (it must be opened explicitly by the user).
    function updatePermalink() {
        try {
            const ref = currentRef();
            const hash = `#ref=${encodeURIComponent(ref.book)}:${ref.chapter}:${ref.verse}&tr=${encodeURIComponent(ref.translation)}`;
            history.replaceState(null, '', location.pathname + location.search + hash);
        } catch (_) {}
    }
    function restoreFromHash() {
        const h = location.hash || '';
        if (!h.length) return;
        const params = new URLSearchParams(h.slice(1));
        const ref = params.get('ref');
        const join = params.get('join');
        const br = currentReader();
        if (ref && br) {
            const m = ref.match(/^([^:]+):(\d+):(\d+)$/);
            if (m) {
                try { br.changeBook && br.changeBook(m[1]); } catch (_) {}
                try { br.changeChapter && br.changeChapter(+m[2]); } catch (_) {}
            }
        }
        // Intentionally do NOT auto-open the study panel from the hash.
        if (join) {
            api('/api/notebooks/join/' + encodeURIComponent(join), { method: 'POST' })
                .then(() => toast('Joined notebook'))
                .catch(() => toast('Could not join (sign in first?)', 'error'));
        }
    }

    // ---- Helpers: current selection / inline interlinear ---------------
    function currentSelectionWord() {
        const sel = window.getSelection && window.getSelection();
        if (!sel || sel.isCollapsed) return '';
        const txt = (sel.toString() || '').trim();
        return txt.split(/\s+/)[0] || '';
    }

    async function applyInterlinear(on) {
        // Add small gloss tooltips beneath Hebrew words in the right-side
        // Hebrew column when enabled.
        document.body.classList.toggle('interlinear-on', !!on);
        if (!on) {
            $$('.interlin-gloss').forEach(g => g.remove());
            return;
        }
        const ref = currentRef();
        try {
            const r = await api(`/api/interlinear/${encodeURIComponent(ref.book)}/${ref.chapter}`);
            // Light-touch: just store on window for popovers to pick up.
            window.__interlinearChapter = r;
        } catch (_) { /* ok */ }
    }

    // ---- Audio bar enhancements: clip download + pause hotkey ---------
    function injectAudioExtras() {
        const bar = $('.audio-controls-bar') || $('#audioBar');
        if (!bar || $('#audio-clip-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'audio-clip-btn';
        btn.className = 'control-btn small';
        btn.title = 'Download verse range as MP3';
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
        btn.addEventListener('click', async () => {
            const ref = currentRef();
            const from = parseInt(prompt('From verse?', String(ref.verse)) || '0', 10);
            if (!from) return;
            const to = parseInt(prompt('To verse?', String(from)) || String(from), 10);
            const url = `/api/clip?book=${encodeURIComponent(ref.book)}&chapter=${ref.chapter}&from=${from}&to=${to}&translation=${encodeURIComponent(ref.translation)}`;
            window.open(url, '_blank');
        });
        bar.appendChild(btn);
    }

    // ---- Footnotes drawer ---------------------------------------------
    async function maybeShowFootnotes() {
        const ref = currentRef();
        try {
            const r = await api(`/api/footnotes/${encodeURIComponent(ref.book)}/${ref.chapter}`);
            const verses = r.verses || {};
            if (!Object.keys(verses).length) return;
            const drawer = $('#footnotes-drawer');
            if (!drawer) return;
            drawer.removeAttribute('hidden');
            $('.footnotes-body', drawer).innerHTML = Object.entries(verses).map(([v, notes]) =>
                `<p><strong>v${esc(v)}.</strong> ${Array.isArray(notes) ? notes.map(esc).join(' • ') : esc(notes)}</p>`,
            ).join('');
        } catch (_) {}
    }

    // ---- Keyboard shortcuts -------------------------------------------
    function bindKeys() {
        document.addEventListener('keydown', (e) => {
            const tag = (e.target && e.target.tagName) || '';
            if (/INPUT|TEXTAREA|SELECT/.test(tag) || e.target.isContentEditable) return;
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const br = currentReader();
            switch (e.key) {
                case 's': case 'S': openPanel(); break;
                case '?': $('#study-keys').toggleAttribute('hidden'); break;
                case 'Escape':
                    closePanel();
                    const k = $('#study-keys'); if (k) k.setAttribute('hidden', '');
                    break;
                case 'd': case 'D': {
                    const on = !document.body.classList.contains('dyslexia');
                    document.body.classList.toggle('dyslexia', on);
                    api('/api/me/settings', { method: 'POST', body: { dyslexia: on?'1':'0' } }).catch(()=>{});
                    break;
                }
                case 'j': case 'J': scrollVerse(1); break;
                case 'k': case 'K': scrollVerse(-1); break;
                case 'n': case 'N': if (br && br.changeChapter) br.changeChapter((br.currentChapter||1)+1); break;
                case 'p': case 'P': if (br && br.changeChapter) br.changeChapter(Math.max(1,(br.currentChapter||1)-1)); break;
                case 'g': case 'G': {
                    const j = $('.nav-jump-button, #navJumpBtn');
                    if (j) j.click();
                    break;
                }
                case 'f': case 'F': openPanel('search'); break;
                case ' ': {
                    const a = document.querySelector('audio');
                    if (a) { e.preventDefault(); a.paused ? a.play() : a.pause(); }
                    break;
                }
            }
        });
    }
    function scrollVerse(dir) {
        const verses = $$('[data-verse]');
        if (!verses.length) return;
        const top = window.innerHeight / 3;
        let curIdx = 0;
        verses.forEach((v, i) => {
            const r = v.getBoundingClientRect();
            if (r.top <= top) curIdx = i;
        });
        const t = verses[Math.max(0, Math.min(verses.length-1, curIdx + dir))];
        if (t) t.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    // ---- PWA -----------------------------------------------------------
    function registerPWA() {
        if (!('serviceWorker' in navigator)) return;
        const link = document.createElement('link');
        link.rel = 'manifest';
        link.href = '/static/manifest.json';
        document.head.appendChild(link);
        navigator.serviceWorker.register('/static/service-worker.js').catch(() => {});
    }

    // ---- Boot ----------------------------------------------------------
    function boot() {
        injectShell();
        bindKeys();
        injectAudioExtras();
        registerPWA();
        // Restore settings.
        api('/api/me/settings').then(r => {
            const s = r.settings || {};
            if (s.dyslexia === '1') document.body.classList.add('dyslexia');
            if (s.largeText === '1') document.body.classList.add('study-large-text');
            if (s.interlinear === '1') applyInterlinear(true);
        }).catch(()=>{});
        // Footnotes drawer + permalink whenever the reader navigates.
        const tick = () => { try { maybeShowFootnotes(); injectAudioExtras(); } catch (_) {} };
        document.addEventListener('chapter:loaded', tick);
        setTimeout(restoreFromHash, 800);
        setInterval(tick, 5000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

    // Expose for debugging.
    window.studyTools = { open: openPanel, close: closePanel, switchTab };
})();
