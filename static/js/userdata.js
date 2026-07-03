/**
 * User data layer: persists reading position, bookmarks, notes and
 * highlights to the server. Identifies the visitor via either a logged-in
 * session cookie or a long-lived anonymous "device key" cookie that the
 * server sets automatically (so anonymous visitors keep their data too).
 *
 * All methods return promises and never throw — callers can safely
 * await them in critical paths (e.g. on chapter change).
 */
class UserData {
    constructor() {
        // In-memory caches keyed for the current chapter so verse-render
        // code can synchronously look up notes/highlights.
        this.notes = new Map();      // verseNum -> {id, body, ...}
        this.highlights = new Map(); // verseNum -> {id, color, ...}
        this.bookmarks = [];         // global list across whole bible
        this._book = null;
        this._chapter = null;
        this._saveTimer = null;
        this._chapterToken = 0;
    }

    async _json(method, url, body) {
        try {
            const opts = {
                method,
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json' },
            };
            if (body !== undefined) {
                opts.headers['Content-Type'] = 'application/json';
                opts.body = JSON.stringify(body);
            }
            const r = await fetch(url, opts);
            if (!r.ok) return null;
            return await r.json();
        } catch (err) {
            console.warn('UserData fetch failed', method, url, err);
            return null;
        }
    }

    /** Get the user's last reading position, or null. */
    async getReadingState() {
        const d = await this._json('GET', '/api/me/state');
        return (d && d.book) ? d : null;
    }

    /** Save the current position + optional reader prefs (debounced). */
    saveReadingState(book, chapter, verse, view, prefs) {
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => {
            this._json('PUT', '/api/me/state', { book, chapter, verse, view, prefs });
        }, 600);
    }

    /** Load all data for the given book+chapter into the caches. */
    async loadForChapter(book, chapter) {
        // Token guards against out-of-order responses if the user changes
        // chapter quickly: only the latest call's data wins.
        const token = ++this._chapterToken;
        this._book = book;
        this._chapter = chapter;
        this.notes.clear();
        this.highlights.clear();
        const [notesResp, hlResp] = await Promise.all([
            this._json('GET', `/api/me/notes?book=${encodeURIComponent(book)}&chapter=${chapter}`),
            this._json('GET', `/api/me/highlights?book=${encodeURIComponent(book)}&chapter=${chapter}`),
        ]);
        if (token !== this._chapterToken) return;
        if (notesResp && Array.isArray(notesResp.notes)) {
            for (const n of notesResp.notes) this.notes.set(String(n.verse), n);
        }
        if (hlResp && Array.isArray(hlResp.highlights)) {
            for (const h of hlResp.highlights) this.highlights.set(String(h.verse), h);
        }
    }

    async loadBookmarks() {
        const d = await this._json('GET', '/api/me/bookmarks');
        this.bookmarks = (d && Array.isArray(d.bookmarks)) ? d.bookmarks : [];
        return this.bookmarks;
    }

    async addBookmark(book, chapter, verse, label) {
        const d = await this._json('POST', '/api/me/bookmarks', { book, chapter, verse, label });
        if (d && d.ok) {
            this.bookmarks.unshift({
                id: d.id, book, chapter, verse, label: label || null,
                created_at: new Date().toISOString(),
            });
        }
        return d && d.ok;
    }

    async removeBookmark(id) {
        const d = await this._json('DELETE', `/api/me/bookmarks/${id}`);
        if (d && d.ok) {
            this.bookmarks = this.bookmarks.filter(b => b.id !== id);
        }
        return d && d.ok;
    }

    isBookmarked(book, chapter, verse) {
        return this.bookmarks.some(b =>
            b.book === book && b.chapter === chapter && +b.verse === +verse);
    }

    async setNote(book, chapter, verse, body) {
        const d = await this._json('POST', '/api/me/notes', { book, chapter, verse, body });
        if (!d || !d.ok) return false;
        if (this._book === book && this._chapter === chapter) {
            const trimmed = (body || '').trim();
            if (!trimmed) {
                this.notes.delete(String(verse));
            } else {
                this.notes.set(String(verse), {
                    id: d.id, book, chapter, verse, body: trimmed,
                    updated_at: new Date().toISOString(),
                });
            }
        }
        return true;
    }

    getNote(verse) { return this.notes.get(String(verse)) || null; }

    async setHighlight(book, chapter, verse, color) {
        const d = await this._json('POST', '/api/me/highlights', { book, chapter, verse, color });
        if (!d || !d.ok) return false;
        if (this._book === book && this._chapter === chapter) {
            if (!color) {
                this.highlights.delete(String(verse));
            } else {
                this.highlights.set(String(verse), { id: d.id, book, chapter, verse, color });
            }
        }
        return true;
    }

    getHighlight(verse) { return this.highlights.get(String(verse)) || null; }
}

window.UserData = UserData;
