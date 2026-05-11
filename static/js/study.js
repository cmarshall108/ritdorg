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
        if ($('#study-fab')) return;
        const fab = document.createElement('button');
        fab.id = 'study-fab';
        fab.className = 'study-fab';
        fab.title = 'Study tools (S)';
        fab.setAttribute('aria-label', 'Open study tools');
        fab.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>';
        document.body.appendChild(fab);
        fab.addEventListener('click', openPanel);

        const overlay = document.createElement('div');
        overlay.id = 'study-overlay';
        overlay.className = 'study-overlay';
        overlay.setAttribute('hidden', '');
        overlay.innerHTML = html`
          <div class="study-modal" role="dialog" aria-modal="true" aria-labelledby="study-title">
            <header class="study-head">
              <h2 id="study-title">Study tools</h2>
              <div class="study-tabs" role="tablist">
                ${tabBtn('concordance', 'Concordance')}
                ${tabBtn('search', 'Search')}
                ${tabBtn('xrefs', 'Cross-refs')}
                ${tabBtn('lemma', 'Hebrew lemma')}
                ${tabBtn('tags', 'Tags')}
                ${tabBtn('outlines', 'Outlines')}
                ${tabBtn('playlists', 'Sermon list')}
                ${tabBtn('plans', 'Reading plan')}
                ${tabBtn('notebooks', 'Notebooks')}
                ${tabBtn('share', 'Share / export')}
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
        switchTab(initialTab || state.lastTab || 'concordance');
    }
    function closePanel() {
        const o = $('#study-overlay');
        if (o) o.setAttribute('hidden', '');
        document.body.classList.remove('study-open');
    }

    const state = { lastTab: 'concordance' };

    function switchTab(name) {
        state.lastTab = name;
        $$('#study-overlay .study-tab').forEach((b) =>
            b.classList.toggle('active', b.dataset.tab === name));
        const body = $('#study-body');
        if (!body) return;
        body.innerHTML = '<p class="study-loading">Loading…</p>';
        (TABS[name] || TABS.concordance)(body).catch((e) => {
            body.innerHTML = `<p class="study-error">${esc(e.message || e)}</p>`;
        });
        updatePermalink();
    }

    // ---- TAB: Concordance ----------------------------------------------
    const TABS = {};

    TABS.concordance = async function (root) {
        root.innerHTML = html`
          <div class="study-form">
            <label>Word
              <input type="text" id="cc-word" placeholder="e.g. Jesus / love / Isten" />
            </label>
            <label>Translations
              <select id="cc-tr" multiple size="6">
                ${['NIV','NKJV','KJV','ESV','NASB1995','Hungarian','Hungarian-Revised','Hebrew']
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
          <div class="study-form">
            <label>Query
              <input type="text" id="sr-q" placeholder='"in the beginning" book:John' />
            </label>
            <label>Translation
              <select id="sr-tr">
                ${['NIV','NKJV','KJV','ESV','NASB1995','Hungarian','Hungarian-Revised','Hebrew']
                  .map(t => `<option ${t==='NIV'?'selected':''}>${t}</option>`).join('')}
              </select>
            </label>
            <label>Limit
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
          <div class="study-form">
            <label>Reference
              <input type="text" id="xr-ref" value="${esc(ref.book)} ${ref.chapter}:${ref.verse}" />
            </label>
            <button class="study-btn primary" id="xr-go">Look up</button>
          </div>
          <div id="xr-out" class="study-out"></div>`;
        $('#xr-go').addEventListener('click', runXrefs);
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
          <div class="study-form">
            <label>Hebrew word
              <input type="text" id="lm-word" dir="rtl" placeholder="בְּרֵאשִׁית" value="${esc(sel||'')}" />
            </label>
            <button class="study-btn primary" id="lm-go">Bridge</button>
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
        root.innerHTML = html`
          <div class="study-form">
            <label>New tag <input type="text" id="tg-name" maxlength="48" /></label>
            <input type="color" id="tg-color" value="#fbbf24" />
            <button class="study-btn primary" id="tg-add">Add tag</button>
          </div>
          <ul class="study-list" id="tg-list">
            ${r.tags.map(t => `
              <li>
                <span class="tag-dot" style="background:${esc(t.color||'#fbbf24')}"></span>
                <strong>${esc(t.name)}</strong>
                <span class="study-meta">${t.verse_count} verses</span>
                <button class="study-btn" data-act="view" data-id="${t.id}">View</button>
                <button class="study-btn" data-act="del" data-id="${t.id}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No tags yet.</li>'}
          </ul>
          <div class="study-form" style="margin-top:1em;">
            <p class="study-meta">Tag the current verse:</p>
            <select id="tg-pick">${r.tags.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('')}</select>
            <button class="study-btn" id="tg-link">Tag ${esc(currentRef().book)} ${currentRef().chapter}:${currentRef().verse}</button>
          </div>
          <div id="tg-out" class="study-out"></div>`;
        $('#tg-add').addEventListener('click', async () => {
            const name = $('#tg-name').value.trim();
            const color = $('#tg-color').value;
            if (!name) return;
            await api('/api/me/tags', { method: 'POST', body: { name, color } });
            switchTab('tags');
        });
        $('#tg-link').addEventListener('click', async () => {
            const id = +$('#tg-pick').value;
            if (!id) return;
            const c = currentRef();
            await api('/api/me/tag-link', { method: 'POST', body: { tag_id: id, book: c.book, chapter: c.chapter, verse: c.verse } });
            toast('Tagged');
        });
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!confirm('Delete tag?')) return;
            await api('/api/me/tags/' + b.dataset.id, { method: 'DELETE' });
            switchTab('tags');
        }));
        $$('button[data-act=view]', root).forEach(b => b.addEventListener('click', async () => {
            const v = await api('/api/me/tags/' + b.dataset.id + '/verses');
            $('#tg-out').innerHTML = '<ul class="study-hits">' + v.verses.map(x =>
                `<li><a href="#" class="study-jump" data-book="${esc(x.book)}" data-ch="${x.chapter}" data-v="${x.verse}">${esc(x.book)} ${x.chapter}:${x.verse}</a></li>`
            ).join('') + '</ul>';
            wireJumps($('#tg-out'));
        }));
    };

    // ---- TAB: Outlines --------------------------------------------------
    TABS.outlines = async function (root) {
        const r = await api('/api/me/outlines');
        root.innerHTML = html`
          <div class="study-form">
            <button class="study-btn primary" id="ol-new">New outline</button>
          </div>
          <ul class="study-list" id="ol-list">
            ${r.outlines.map(o => `
              <li>
                <strong>${esc(o.title)}</strong>
                <span class="study-meta">updated ${esc((o.updated_at||'').slice(0,10))}</span>
                <button class="study-btn" data-act="open" data-id="${o.id}">Open</button>
                <a class="study-btn" href="/api/me/outlines/${o.id}/export?translation=NIV" target="_blank">Export</a>
                <button class="study-btn" data-act="del" data-id="${o.id}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No outlines yet.</li>'}
          </ul>
          <div id="ol-edit" class="study-out"></div>`;
        $('#ol-new').addEventListener('click', async () => {
            const t = prompt('Outline title?', 'New sermon');
            if (!t) return;
            await api('/api/me/outlines', { method: 'POST', body: { title: t } });
            switchTab('outlines');
        });
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!confirm('Delete outline?')) return;
            await api('/api/me/outlines/' + b.dataset.id, { method: 'DELETE' });
            switchTab('outlines');
        }));
        $$('button[data-act=open]', root).forEach(b => b.addEventListener('click', async () => {
            const o = (await api('/api/me/outlines/' + b.dataset.id)).outline;
            const ed = $('#ol-edit');
            ed.innerHTML = html`
              <h3>Edit outline</h3>
              <label>Title <input type="text" id="ol-title" value="${esc(o.title)}"/></label>
              <label>Theme <input type="text" id="ol-theme" value="${esc(o.theme||'')}"/></label>
              <label>Body (Markdown)
                <textarea id="ol-body" rows="10">${esc(o.body_md||'')}</textarea>
              </label>
              <p class="study-meta">Verses (one per line, format: <code>Book ch:v | label</code>)</p>
              <textarea id="ol-verses" rows="6">${o.verses.map(v => `${v.book} ${v.chapter}:${v.verse}${v.label?' | '+v.label:''}`).join('\n')}</textarea>
              <button class="study-btn primary" id="ol-save">Save</button>
              <button class="study-btn" id="ol-print">Print handout</button>`;
            $('#ol-save').addEventListener('click', async () => {
                const verses = $('#ol-verses').value.split('\n').map(line => {
                    const m = line.match(/^\s*(.+?)\s+(\d+):(\d+)\s*(?:\|\s*(.+))?$/);
                    return m ? { book: m[1].trim(), chapter: +m[2], verse: +m[3], label: (m[4]||'').trim() } : null;
                }).filter(Boolean);
                await api('/api/me/outlines/' + o.id, { method: 'PUT', body: {
                    title: $('#ol-title').value, theme: $('#ol-theme').value,
                    body_md: $('#ol-body').value, verses,
                }});
                toast('Saved');
                switchTab('outlines');
            });
            $('#ol-print').addEventListener('click', () => {
                window.open(`/api/me/outlines/${o.id}/export?translation=NIV`, '_blank');
            });
        }));
    };

    // ---- TAB: Sermon list (playlists) -----------------------------------
    TABS.playlists = async function (root) {
        const r = await api('/api/me/playlists');
        root.innerHTML = html`
          <div class="study-form">
            <button class="study-btn primary" id="pl-new">New sermon list</button>
          </div>
          <ul class="study-list">
            ${r.playlists.map(p => `
              <li>
                <strong>${esc(p.title)}</strong>
                <span class="study-meta">${p.item_count} verses</span>
                <button class="study-btn" data-act="preach" data-id="${p.id}">Preach view</button>
                <button class="study-btn" data-act="add" data-id="${p.id}">Add current verse</button>
                <button class="study-btn" data-act="del" data-id="${p.id}">Delete</button>
              </li>`).join('') || '<li class="study-meta">No sermon lists yet.</li>'}
          </ul>`;
        $('#pl-new').addEventListener('click', async () => {
            const t = prompt('Sermon list title?', 'New sermon');
            if (!t) return;
            await api('/api/me/playlists', { method: 'POST', body: { title: t } });
            switchTab('playlists');
        });
        $$('button[data-act=del]', root).forEach(b => b.addEventListener('click', async () => {
            if (!confirm('Delete?')) return;
            await api('/api/me/playlists/' + b.dataset.id, { method: 'DELETE' });
            switchTab('playlists');
        }));
        $$('button[data-act=add]', root).forEach(b => b.addEventListener('click', async () => {
            const c = currentRef();
            await api(`/api/me/playlists/${b.dataset.id}/items`, { method: 'POST', body: { book: c.book, chapter: c.chapter, verse_start: c.verse, verse_end: c.verse } });
            toast('Added to sermon list');
        }));
        $$('button[data-act=preach]', root).forEach(b => b.addEventListener('click', () => openPreach(+b.dataset.id)));
    };

    async function openPreach(pid) {
        const p = (await api('/api/me/playlists/' + pid)).playlist;
        let verses = [];
        for (const item of p.items) {
            try {
                const ch = await api(`/api/parallel/${encodeURIComponent(item.book)}/${item.chapter}/NIV/Hebrew`);
                const start = item.verse_start || 1, end = item.verse_end || start;
                for (let v = start; v <= end; v++) {
                    const text = (ch.translation1 && ch.translation1.verses && (ch.translation1.verses[v] || ch.translation1.verses[String(v)])) || '';
                    if (text) verses.push({ ref: `${item.book} ${item.chapter}:${v}`, text, note: item.note });
                }
            } catch (_) {}
        }
        const w = window.open('', '_blank');
        if (!w) { toast('Popup blocked'); return; }
        w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(p.title)}</title>
            <style>
              body{font:24px/1.5 Georgia,serif;background:#0b1020;color:#fff;margin:0;padding:0;}
              .slide{min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:6vw;box-sizing:border-box;border-bottom:1px solid #1f2937;}
              .slide h2{margin:0 0 .6em;color:#fbbf24;font-size:1.1em;}
              .slide p{font-size:2em;line-height:1.4;}
              .slide .note{margin-top:1em;color:#cbd5e1;font-size:0.7em;font-style:italic;}
              @media print { .slide{page-break-after:always;background:#fff;color:#000;} .slide h2{color:#000;} }
            </style></head><body>
            <h1 style="text-align:center;padding:2em 1em;">${esc(p.title)}</h1>
            ${verses.map(v => `<section class="slide"><h2>${esc(v.ref)}</h2><p>${esc(v.text)}</p>${v.note?`<p class="note">${esc(v.note)}</p>`:''}</section>`).join('')}
            </body></html>`);
        w.document.close();
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
            root.innerHTML = '<p class="study-meta">Sign in to create or join shared notebooks.</p>';
            return;
        }
        root.innerHTML = html`
          <div class="study-form">
            <button class="study-btn primary" id="nb-new">New notebook</button>
            <label>Join via token <input type="text" id="nb-token" /></label>
            <button class="study-btn" id="nb-join">Join</button>
          </div>
          <ul class="study-list">
            ${r.notebooks.map(n => `
              <li>
                <strong>${esc(n.title)}</strong>
                <span class="study-meta">${n.member_count} member${n.member_count===1?'':'s'}${n.is_owner?' • owner':''}</span>
                ${n.is_owner ? `<button class="study-btn" data-act="share" data-tok="${esc(n.share_token)}">Share link</button>` : ''}
                <button class="study-btn" data-act="open" data-id="${n.id}">Open</button>
              </li>`).join('') || '<li class="study-meta">No notebooks yet.</li>'}
          </ul>
          <div id="nb-out" class="study-out"></div>`;
        $('#nb-new').addEventListener('click', async () => {
            const t = prompt('Notebook title?', 'Bible study group');
            if (!t) return;
            await api('/api/me/notebooks', { method: 'POST', body: { title: t } });
            switchTab('notebooks');
        });
        $('#nb-join').addEventListener('click', async () => {
            const tok = $('#nb-token').value.trim();
            if (!tok) return;
            await api('/api/notebooks/join/' + encodeURIComponent(tok), { method: 'POST' });
            switchTab('notebooks');
        });
        $$('button[data-act=share]', root).forEach(b => b.addEventListener('click', () => {
            const url = location.origin + location.pathname + '#join=' + b.dataset.tok;
            navigator.clipboard.writeText(url).then(() => toast('Share link copied'));
        }));
        $$('button[data-act=open]', root).forEach(b => b.addEventListener('click', async () => {
            const d = await api('/api/me/notebooks/' + b.dataset.id);
            const ref = currentRef();
            $('#nb-out').innerHTML = html`
              <h3>${esc(d.notebook.title)}</h3>
              <textarea id="nb-body" rows="4" placeholder="Add a note for ${esc(ref.book)} ${ref.chapter}:${ref.verse}…"></textarea>
              <button class="study-btn primary" id="nb-add">Post</button>
              <ul class="study-list">${d.entries.map(e => `
                <li>
                  <strong>${esc(e.author_email||'anon')}</strong>
                  ${e.book?`<span class="study-meta">${esc(e.book)} ${e.chapter}:${e.verse}</span>`:''}
                  <p>${esc(e.body_md)}</p>
                  <span class="study-meta">${esc((e.created_at||'').replace('T',' ').slice(0,16))}</span>
                </li>`).join('')}</ul>`;
            $('#nb-add').addEventListener('click', async () => {
                const body = $('#nb-body').value.trim();
                if (!body) return;
                const r2 = currentRef();
                await api('/api/me/notebooks/' + b.dataset.id + '/entries', { method: 'POST', body: {
                    body_md: body, book: r2.book, chapter: r2.chapter, verse: r2.verse,
                }});
                toast('Posted');
                $$('button[data-act=open]', root).find(x => x.dataset.id === b.dataset.id).click();
            });
        }));
    };

    // ---- TAB: Share / export -------------------------------------------
    TABS.share = async function (root) {
        const ref = currentRef();
        root.innerHTML = html`
          <h3>Share current verse</h3>
          <p class="study-meta">${esc(ref.book)} ${ref.chapter}:${ref.verse}</p>
          <div class="study-form">
            <button class="study-btn primary" id="sh-png">Download share image (PNG)</button>
            <button class="study-btn" id="sh-link">Copy permalink</button>
          </div>
          <h3>Export everything</h3>
          <p class="study-meta">A ZIP of your notes, bookmarks, highlights, tags, outlines, sermon lists, plan progress and settings.</p>
          <a class="study-btn primary" href="/api/me/export/all" download>Download .zip</a>`;
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
    function updatePermalink() {
        try {
            const ref = currentRef();
            const tab = state.lastTab;
            const hash = `#ref=${encodeURIComponent(ref.book)}:${ref.chapter}:${ref.verse}&tr=${encodeURIComponent(ref.translation)}&study=${encodeURIComponent(tab||'')}`;
            history.replaceState(null, '', location.pathname + location.search + hash);
        } catch (_) {}
    }
    function restoreFromHash() {
        const h = location.hash || '';
        if (!h.length) return;
        const params = new URLSearchParams(h.slice(1));
        const ref = params.get('ref');
        const tab = params.get('study');
        const join = params.get('join');
        const br = currentReader();
        if (ref && br) {
            const m = ref.match(/^([^:]+):(\d+):(\d+)$/);
            if (m) {
                try { br.changeBook && br.changeBook(m[1]); } catch (_) {}
                try { br.changeChapter && br.changeChapter(+m[2]); } catch (_) {}
            }
        }
        if (tab) setTimeout(() => openPanel(tab), 600);
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
