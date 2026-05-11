// ===== RITDorg - Interactive Bible Reader =====

class BibleReader {
    constructor() {
        this.currentBook = 'Matthew';
        this.currentChapter = 1;
        this.currentPage = 0;
        this.verses = {};
        this.pagesContent = [];
        this.versesPerPage = 8;
        this.isAnimating = false;
        this.fontSize = 'medium';
        this.currentTranslation = 'NIV';
        
        // Parallel translations
        this.parallelTrans1 = 'NIV';
        this.parallelTrans2 = 'Hebrew';
        this.parallelVerses1 = {};
        this.parallelVerses2 = {};
        this.allTranslations = []; // Will be populated from the dropdown options
        
        // Video sync translations (Hebrew audio, show NIV + Hebrew text)
        this.syncTrans1 = 'NIV';
        this.syncTrans2 = 'Hebrew';
        
        // Video sync
        this.player = null;
        this.isPlayerReady = false;
        this.syncData = null;
        this.syncInterval = null;
        this.playbackRate = 1; // default playback rate
        
        // Browser TTS fallback (used when no video for a chapter)
        this.ttsState = 'idle'; // 'idle' | 'playing' | 'paused'
        this.ttsQueue = [];
        this.ttsIndex = 0;
        this.currentUtterance = null;

        // User-configurable voice settings (Voice settings dialog).
        // - voice:        device (browser) voice URI per language
        // - onlineVoice:  preferred Microsoft Edge neural voice per language
        // - preferServer: prefer the (much more natural) online voices over
        //                 device voices. Default ON because Edge neural is
        //                 dramatically better than most browser voices.
        // - tld:          legacy gTTS accent (only used when fallback
        //                 reaches gTTS)
        this.ttsSettings = (() => {
            const def = {
                voice:       { en: '', hu: '', he: '' },
                onlineVoice: { en: '', hu: '', he: '' },
                preferServer: true,
                tld: 'com',
            };
            try {
                const raw = localStorage.getItem('ttsSettings');
                if (!raw) return def;
                const parsed = JSON.parse(raw);
                return {
                    voice:        { ...def.voice,       ...(parsed.voice || {}) },
                    onlineVoice:  { ...def.onlineVoice, ...(parsed.onlineVoice || {}) },
                    preferServer: parsed.preferServer === undefined ? true : !!parsed.preferServer,
                    tld:          parsed.tld || def.tld,
                };
            } catch { return def; }
        })();

        // Auto-advance to the next chapter when read-aloud (or video) finishes.
        // Defaults ON; persisted across sessions.
        this.autoAdvanceChapter = (() => {
            try {
                const v = localStorage.getItem('autoAdvanceChapter');
                return v === null ? true : v === '1';
            } catch { return true; }
        })();
        this._autoplayAfterLoad = false;

        // Hebrew column on/off (persisted). When disabled, the right
        // (Hebrew) column is hidden and the play button drives TTS for the
        // left translation instead of playing the Hebrew-narrated video.
        this.hebrewDisabled = (() => {
            try { return localStorage.getItem('hebrewDisabled') === '1'; }
            catch { return false; }
        })();
        
        // Dynamic caption sync
        this.captions = null;
        this.currentCaptionIndex = -1;
        this.lastHighlightedVerse = null;
        this.lastCaptionText = null;
        this.verseStartTimes = new Map();
        this.lastCaptionVideoId = null;
        this.captionFetchToken = 0;
        this.focusModeEnabled = localStorage.getItem('focusReadingMode') === 'true';

        // Caption→verse matching helpers
        this.verseIndex = null;          // { byVerse, idf, verseNums }
        this.recentVerseMatches = [];    // last few verse matches for smoothing

        // Per-visitor data: bookmarks, notes, highlights, last position.
        this.userData = (typeof UserData !== 'undefined') ? new UserData() : null;

        this.init();
    }
    
    init() {
        this.searchDebounceTimer = null;
        // Generation counters for in-flight fetches; bumped each call so
        // a stale response can't overwrite the current view.
        this._chapterReqId = 0;
        this._parallelReqId = 0;
        this._syncReqId = 0;
        this.bindEvents();

        // Initialize playback rate UI
        const rateSlider = document.getElementById('rateSlider');
        if (rateSlider) {
            rateSlider.value = this.playbackRate;
            const rateLabel = document.getElementById('rateLabel');
            if (rateLabel) rateLabel.textContent = `${this.playbackRate}×`;
        }

        this.applyFocusMode(this.focusModeEnabled);
        
        // Set dropdown to match default book
        document.getElementById('bookSelect').value = this.currentBook;
        
        // Initialize translation options to prevent same selection
        this.updateTranslationOptions();
        
        // Restore last-read position (if any) before kicking off the
        // initial chapter load. Resume is best-effort — on any error or
        // unknown book we silently fall back to the current defaults.
        this.setupUserDataUI();
        this._restoreReadingState().finally(() => {
            document.getElementById('bookSelect').value = this.currentBook;
            this.updateTranslationOptions();
            this.loadChapters(this.currentBook, this.currentChapter);
            if (this.userData) {
                this.userData.loadBookmarks().then(() => this._renderBookmarksList());
            }
        });
    }
    
    bindEvents() {
        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('sidebar');
        
        if (sidebarToggle && sidebar) {
            // Restore collapsed state from localStorage
            const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            if (isCollapsed) {
                sidebar.classList.add('collapsed');
            }
            
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('collapsed');
                // On mobile the sidebar uses .open instead of .collapsed; toggle both for safety.
                sidebar.classList.toggle('open');
                this._syncSidebarBackdrop();
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            });
        }

        // Mobile sidebar backdrop — tap outside to close.
        const sidebarBackdrop = document.getElementById('sidebarBackdrop');
        if (sidebarBackdrop) {
            sidebarBackdrop.addEventListener('click', () => {
                document.getElementById('sidebar')?.classList.remove('open');
                document.getElementById('topNav')?.classList.remove('open');
                document.getElementById('mobileMenuToggle')?.setAttribute('aria-expanded', 'false');
                this._syncSidebarBackdrop();
            });
        }
        
        // Navigation
        document.getElementById('bookSelect').addEventListener('change', (e) => {
            this.currentBook = e.target.value;
            this.loadChapters(this.currentBook);
        });
        
        document.getElementById('chapterSelect').addEventListener('change', (e) => {
            this.currentChapter = parseInt(e.target.value);
            this.loadChapter(this.currentBook, this.currentChapter);
        });

        // Mobile top-bar controls (mirror sidebar selectors)
        const mobileMenuToggle = document.getElementById('mobileMenuToggle');
        const topNav = document.getElementById('topNav');
        if (mobileMenuToggle && topNav) {
            mobileMenuToggle.addEventListener('click', () => {
                const isOpen = topNav.classList.toggle('open');
                mobileMenuToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                this._syncSidebarBackdrop();
            });
            topNav.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', () => {
                    topNav.classList.remove('open');
                    mobileMenuToggle.setAttribute('aria-expanded', 'false');
                });
            });
        }

        const mobileBookSelect = document.getElementById('mobileBookSelect');
        if (mobileBookSelect) {
            mobileBookSelect.addEventListener('change', (e) => {
                const book = e.target.value;
                this.currentBook = book;
                const sidebarSel = document.getElementById('bookSelect');
                if (sidebarSel) sidebarSel.value = book;
                this.loadChapters(book);
            });
        }

        const mobileChapterSelect = document.getElementById('mobileChapterSelect');
        if (mobileChapterSelect) {
            mobileChapterSelect.addEventListener('change', (e) => {
                const chapter = parseInt(e.target.value);
                this.currentChapter = chapter;
                const sidebarSel = document.getElementById('chapterSelect');
                if (sidebarSel) sidebarSel.value = String(chapter);
                this.loadChapter(this.currentBook, chapter);
            });
        }

        const mobileVerseSelect = document.getElementById('mobileVerseSelect');
        if (mobileVerseSelect) {
            mobileVerseSelect.addEventListener('change', (e) => {
                const verseNum = e.target.value;
                if (!verseNum) return;
                this.scrollToVerse(parseInt(verseNum));
            });
        }

        // Bottom-bar verse selector (visible in focus mode and on mobile)
        this.setupNavJumpPopover();
        
        // Page navigation
        document.getElementById('prevPage').addEventListener('click', () => this.prevPage());
        document.getElementById('nextPage').addEventListener('click', () => this.nextPage());
        
        // Keyboard navigation. Skip when typing in form fields so the
        // search box and translation dropdowns don't accidentally flip
        // pages on every arrow press.
        document.addEventListener('keydown', (e) => {
            const t = e.target;
            if (t && (t.matches('input, textarea, select, [contenteditable="true"]')
                      || t.isContentEditable)) return;
            if (e.key === 'ArrowLeft') this.prevPage();
            if (e.key === 'ArrowRight') this.nextPage();
        });
        
        // Quick navigation
        document.querySelectorAll('.quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const book = btn.dataset.book;
                const chapter = parseInt(btn.dataset.chapter);
                document.getElementById('bookSelect').value = book;
                this.currentBook = book;
                this.loadChapters(book, chapter);
            });
        });
        
        // View toggle
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const view = btn.dataset.view;
                document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                document.getElementById('readerView').classList.toggle('active', view === 'reader');
                document.getElementById('parallelView').classList.toggle('active', view === 'parallel');
                document.getElementById('videoView').classList.toggle('active', view === 'video');
                
                if (view === 'parallel') {
                    this.loadParallelVerses();
                } else if (view === 'video') {
                    this.loadVideoSync();
                }
            });
        });
        
        // Parallel translation selectors
        document.getElementById('parallelTrans1').addEventListener('change', (e) => {
            this.parallelTrans1 = e.target.value;
            this.updateTranslationOptions();
            this.loadParallelVerses();
        });
        
        document.getElementById('parallelTrans2').addEventListener('change', (e) => {
            this.parallelTrans2 = e.target.value;
            this.updateTranslationOptions();
            this.loadParallelVerses();
        });
        
        // Swap translations button (parallel view)
        const swapBtn = document.getElementById('swapTranslations');
        if (swapBtn) {
            swapBtn.addEventListener('click', () => {
                const a = this.parallelTrans1;
                const b = this.parallelTrans2;
                this.parallelTrans1 = b;
                this.parallelTrans2 = a;
                const sel1 = document.getElementById('parallelTrans1');
                const sel2 = document.getElementById('parallelTrans2');
                if (sel1) sel1.value = b;
                if (sel2) sel2.value = a;
                swapBtn.classList.remove('swap-anim');
                // Force reflow to restart the animation
                void swapBtn.offsetWidth;
                swapBtn.classList.add('swap-anim');
                this.updateTranslationOptions();
                this.loadParallelVerses();
            });
        }

        // Sync translation selectors (both editable; either side can be Hebrew)
        document.getElementById('syncTrans1').addEventListener('change', (e) => {
            this.syncTrans1 = e.target.value;
            document.getElementById('syncColName1').textContent = this.syncTrans1;
            this.renderSyncText();
        });

        const syncTrans2Select = document.getElementById('syncTrans2');
        if (syncTrans2Select) {
            syncTrans2Select.disabled = false;
            syncTrans2Select.addEventListener('change', (e) => {
                this.syncTrans2 = e.target.value;
                document.getElementById('syncColName2').textContent = this.syncTrans2;
                this.renderSyncText();
            });
        }

        // Swap translations button (sync / video view)
        const swapSyncBtn = document.getElementById('swapSyncTranslations');
        if (swapSyncBtn) {
            swapSyncBtn.addEventListener('click', () => {
                const a = this.syncTrans1;
                const b = this.syncTrans2;
                this.syncTrans1 = b;
                this.syncTrans2 = a;
                const s1 = document.getElementById('syncTrans1');
                const s2 = document.getElementById('syncTrans2');
                if (s1) s1.value = b;
                if (s2) s2.value = a;
                document.getElementById('syncColName1').textContent = this.syncTrans1;
                document.getElementById('syncColName2').textContent = this.syncTrans2;
                swapSyncBtn.classList.remove('swap-anim');
                void swapSyncBtn.offsetWidth;
                swapSyncBtn.classList.add('swap-anim');
                this.renderSyncText();
            });
        }

        // (legacy) Filter syncTrans1 options — now a no-op preserving selections
        this.updateSyncTranslationOptions();
        
        // Font size
        document.querySelectorAll('.size-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.setFontSize(btn.dataset.size);
            });
        });
        
        // Video controls
        document.getElementById('playPauseBtn').addEventListener('click', () => this.togglePlay());
        document.querySelector('.progress-bar').addEventListener('click', (e) => this.seekVideo(e));

        // Playback rate slider
        const rateSlider = document.getElementById('rateSlider');
        if (rateSlider) {
            rateSlider.addEventListener('input', (e) => {
                const r = parseFloat(e.target.value);
                this.setPlaybackRate(r);
            });
        }
        
        // Video visibility toggle
        document.getElementById('videoToggleBtn').addEventListener('click', () => this.toggleVideoVisibility());

        // Hebrew column on/off toggle
        const hebrewToggleBtn = document.getElementById('hebrewToggleBtn');
        if (hebrewToggleBtn) {
            const setBtnState = () => {
                hebrewToggleBtn.classList.toggle('active', !this.hebrewDisabled);
                hebrewToggleBtn.setAttribute('aria-pressed', String(!this.hebrewDisabled));
            };
            setBtnState();
            hebrewToggleBtn.addEventListener('click', () => {
                this.hebrewDisabled = !this.hebrewDisabled;
                try { localStorage.setItem('hebrewDisabled', this.hebrewDisabled ? '1' : '0'); } catch {}
                setBtnState();
                // Stop any video playback if user is turning Hebrew off
                if (this.hebrewDisabled && this.player && this.isPlayerReady) {
                    try { this.player.pauseVideo(); } catch {}
                }
                // Re-apply column visibility immediately
                this.applySyncColumnVisibility(false, false);
            });
        }

        const focusModeBtn = document.getElementById('focusModeBtn');
        if (focusModeBtn) {
            focusModeBtn.addEventListener('click', () => this.toggleFocusMode());
        }

        // Voice / TTS settings dialog
        this.bindTTSSettings();

        // Hebrew word definition popover
        this.bindHebrewWordLookup();
        // Generic word study popover (count + optional pronunciation)
        this.bindGenericWordLookup();

        // Pastor study tools (per-verse menu + Study Tools dialog).
        this.bindVerseActions();
        this.bindStudyTools();
        
        // Chapter navigation
        document.getElementById('prevChapterBtn').addEventListener('click', () => this.prevChapter());
        document.getElementById('nextChapterBtn').addEventListener('click', () => this.nextChapter());
        const autoBtn = document.getElementById('autoAdvanceBtn');
        if (autoBtn) {
            // Reflect persisted state immediately.
            autoBtn.classList.toggle('active', !!this.autoAdvanceChapter);
            autoBtn.setAttribute('aria-pressed', this.autoAdvanceChapter ? 'true' : 'false');
            autoBtn.addEventListener('click', () => {
                this.autoAdvanceChapter = !this.autoAdvanceChapter;
                try { localStorage.setItem('autoAdvanceChapter', this.autoAdvanceChapter ? '1' : '0'); } catch {}
                autoBtn.classList.toggle('active', this.autoAdvanceChapter);
                autoBtn.setAttribute('aria-pressed', this.autoAdvanceChapter ? 'true' : 'false');
                this.showToast(
                    this.autoAdvanceChapter ? 'Auto-continue: ON' : 'Auto-continue: OFF',
                    'info'
                );
            });
        }

        // Search
        const searchInput = document.getElementById('searchInput');
        const searchClear = document.getElementById('searchClear');
        const searchClose = document.getElementById('searchClose');
        if (searchInput) {
            searchInput.addEventListener('input', () => this.onSearchInput());
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.performSearch();
                }
                if (e.key === 'Escape') {
                    this.closeSearch();
                }
            });
        }
        if (searchClear) {
            searchClear.addEventListener('click', () => this.clearSearch());
        }
        if (searchClose) {
            searchClose.addEventListener('click', () => this.closeSearch());
        }
        document.getElementById('searchTranslation')?.addEventListener('change', () => {
            if (document.getElementById('searchInput').value.trim().length >= 2) {
                this.performSearch();
            }
        });
    }
    
    prevChapter() {
        if (this.currentChapter > 1) {
            this.currentChapter--;
            document.getElementById('chapterSelect').value = this.currentChapter;
            this.loadChapter(this.currentBook, this.currentChapter);
        }
    }
    
    nextChapter() {
        const chapterSelect = document.getElementById('chapterSelect');
        const maxChapter = chapterSelect.options.length;
        if (this.currentChapter < maxChapter) {
            this.currentChapter++;
            chapterSelect.value = this.currentChapter;
            this.loadChapter(this.currentBook, this.currentChapter);
        }
    }
    
    toggleVideoVisibility() {
        const videoWrapper = document.querySelector('.video-player-wrapper');
        const contentArea = document.querySelector('.video-content-area');
        const toggleBtn = document.getElementById('videoToggleBtn');
        
        if (videoWrapper.classList.contains('hidden-player')) {
            // Show video - side by side layout
            videoWrapper.classList.remove('hidden-player');
            videoWrapper.classList.add('visible-player');
            contentArea.classList.add('side-by-side');
            toggleBtn.classList.add('active');
        } else {
            // Hide video - text only layout
            videoWrapper.classList.remove('visible-player');
            videoWrapper.classList.add('hidden-player');
            contentArea.classList.remove('side-by-side');
            toggleBtn.classList.remove('active');
        }
    }

    toggleFocusMode() {
        this.focusModeEnabled = !this.focusModeEnabled;
        this.applyFocusMode(this.focusModeEnabled);
    }

    applyFocusMode(enabled) {
        document.body.classList.toggle('focus-reading-mode', enabled);

        const focusBtn = document.getElementById('focusModeBtn');
        if (focusBtn) {
            focusBtn.classList.toggle('active', enabled);
            focusBtn.setAttribute('aria-pressed', enabled ? 'true' : 'false');
            focusBtn.title = enabled ? 'Exit focus mode' : 'Focus mode: hide top bars';
        }

        localStorage.setItem('focusReadingMode', enabled ? 'true' : 'false');
    }
    
    async loadChapters(book, selectChapter = 1) {
        try {
            const response = await fetch(`/api/chapters/${book}`);
            const chapters = await response.json();
            
            const select = document.getElementById('chapterSelect');
            select.innerHTML = chapters.map(ch => 
                `<option value="${ch}" ${ch === selectChapter ? 'selected' : ''}>Chapter ${ch}</option>`
            ).join('');

            const mobileSelect = document.getElementById('mobileChapterSelect');
            if (mobileSelect) {
                mobileSelect.innerHTML = chapters.map(ch =>
                    `<option value="${ch}" ${ch === selectChapter ? 'selected' : ''}>Ch ${ch}</option>`
                ).join('');
            }
            const mobileBook = document.getElementById('mobileBookSelect');
            if (mobileBook && mobileBook.value !== book) mobileBook.value = book;
            
            this.currentChapter = selectChapter;
            this.loadChapter(book, selectChapter);
        } catch (error) {
            console.error('Failed to load chapters:', error);
            this.showToast('Failed to load chapters', 'error');
        }
    }
    
    async loadChapter(book, chapter) {
        try {
            // Stop any in-progress text-to-speech playback when changing chapter
            if (this.ttsState && this.ttsState !== 'idle') this.stopTTS();
            const reqId = ++this._chapterReqId;
            const response = await fetch(`/api/verses/${book}/${chapter}?translation=${this.currentTranslation}`);
            const data = await response.json();
            // Bail if a newer chapter request was issued while this one was in flight.
            if (reqId !== this._chapterReqId) return;
            // Handle new response format with fallback info
            this.verses = data.verses || data;
            
            // Show fallback notice if applicable
            if (data.fallback) {
                this.showToast(`${data.requested} not available for this passage. Showing ${data.translation}.`, 'info');
            }
            
            this.currentBook = book;
            this.currentChapter = chapter;
            this.currentPage = 0;
            
            this.paginateVerses();
            this.renderCurrentPages();
            this.updateNavigation();
            this.populateMobileVerseSelect();
            
            // Update headers
            document.getElementById('leftBookName').textContent = book;
            document.getElementById('rightBookName').textContent = book;
            document.getElementById('leftChapterNum').textContent = `Chapter ${chapter}`;
            document.getElementById('rightChapterNum').textContent = `Chapter ${chapter}`;
            
            // Update parallel view if active
            if (document.getElementById('parallelView').classList.contains('active')) {
                this.loadParallelVerses();
            }
            
            // Update video view if active
            if (document.getElementById('videoView').classList.contains('active')) {
                await this.loadVideoSync();
            }

            // Highlight verse from search navigation
            this.highlightPendingVerse();

            // Persist last-read position and load per-chapter annotations
            // (highlights, notes). Bookmarks are global so we don't refetch.
            if (this.userData) {
                this.userData.saveReadingState(book, chapter, null, this._currentViewName());
                this.userData.loadForChapter(book, chapter).then(() => {
                    this._applyVerseAnnotations();
                });
            }

            // If we got here via auto-continue from the previous chapter,
            // resume read-aloud playback automatically. We delay slightly so
            // the new chapter's verse DOM (and any video re-init) is ready.
            if (this._autoplayAfterLoad) {
                this._autoplayAfterLoad = false;
                setTimeout(() => {
                    try {
                        // Prefer the same play path the user normally uses
                        // (video if available, otherwise TTS).
                        this.togglePlay();
                    } catch (e) {
                        console.warn('auto-advance togglePlay failed', e);
                        try { this.startTTS(); } catch {}
                    }
                }, 250);
            }

        } catch (error) {
            console.error('Failed to load verses:', error);
            this.showToast('Failed to load verses', 'error');
            // If we were mid auto-advance, abort it so a stale flag doesn't
            // surprise the user the next time they manually change chapter.
            this._autoplayAfterLoad = false;
        }
    }
    
    paginateVerses() {
        const verseNums = Object.keys(this.verses).map(Number).sort((a, b) => a - b);
        this.pagesContent = [];
        
        for (let i = 0; i < verseNums.length; i += this.versesPerPage) {
            const pageVerses = verseNums.slice(i, i + this.versesPerPage);
            this.pagesContent.push(pageVerses);
        }
        
        // Ensure even number of pages for book spread
        if (this.pagesContent.length % 2 !== 0) {
            this.pagesContent.push([]);
        }
    }
    
    renderCurrentPages() {
        const leftPage = this.pagesContent[this.currentPage] || [];
        const rightPage = this.pagesContent[this.currentPage + 1] || [];
        
        document.getElementById('leftVerses').innerHTML = this.renderVerses(leftPage);
        document.getElementById('rightVerses').innerHTML = this.renderVerses(rightPage);
        
        document.getElementById('leftPageNum').textContent = this.currentPage + 1;
        document.getElementById('rightPageNum').textContent = this.currentPage + 2;
    }
    
    renderVerses(verseNums) {
        if (verseNums.length === 0) {
            return '<p class="empty-page" style="color: var(--text-muted); font-style: italic; text-align: center; margin-top: 40%;">End of chapter</p>';
        }
        const HEB = /[\u0590-\u05FF]/;
        return verseNums.map(num => {
            const text = this.verses[num] || '';
            const body = text.split(' ').map(w => HEB.test(w)
                ? this._wrapHebrewToken(w)
                : this._wrapWordToken(w)
            ).join(' ');
            return `
            <p class="verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                ${body}
            </p>
        `;
        }).join('');
    }
    
    updateNavigation() {
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        
        prevBtn.disabled = this.currentPage === 0;
        nextBtn.disabled = this.currentPage >= this.pagesContent.length - 2;
    }
    
    nextPage() {
        if (this.isAnimating || this.currentPage >= this.pagesContent.length - 2) return;
        this.clearSearchHighlight();
        
        this.isAnimating = true;
        const turningPage = document.getElementById('pageTurning');
        
        // Set content for turning page
        const frontContent = this.renderVerses(this.pagesContent[this.currentPage + 1] || []);
        const backContent = this.renderVerses(this.pagesContent[this.currentPage + 2] || []);
        
        turningPage.querySelector('.page-front .page-content').innerHTML = `
            <div class="page-header">
                <span class="book-name">${this.currentBook}</span>
                <span class="chapter-num">Chapter ${this.currentChapter}</span>
            </div>
            <div class="verses">${frontContent}</div>
        `;
        
        turningPage.querySelector('.page-back .page-content').innerHTML = `
            <div class="page-header">
                <span class="book-name">${this.currentBook}</span>
                <span class="chapter-num">Chapter ${this.currentChapter}</span>
            </div>
            <div class="verses">${backContent}</div>
        `;
        
        turningPage.classList.add('turning-forward');
        
        setTimeout(() => {
            this.currentPage += 2;
            this.renderCurrentPages();
            this.updateNavigation();
            turningPage.classList.remove('turning-forward');
            this.isAnimating = false;
        }, 800);
    }
    
    prevPage() {
        if (this.isAnimating || this.currentPage === 0) return;
        this.clearSearchHighlight();
        
        this.isAnimating = true;
        const turningPage = document.getElementById('pageTurning');
        
        // Set content for turning page (going backwards)
        const frontContent = this.renderVerses(this.pagesContent[this.currentPage - 1] || []);
        const backContent = this.renderVerses(this.pagesContent[this.currentPage] || []);
        
        turningPage.querySelector('.page-front .page-content').innerHTML = `
            <div class="page-header">
                <span class="book-name">${this.currentBook}</span>
                <span class="chapter-num">Chapter ${this.currentChapter}</span>
            </div>
            <div class="verses">${frontContent}</div>
        `;
        
        turningPage.querySelector('.page-back .page-content').innerHTML = `
            <div class="page-header">
                <span class="book-name">${this.currentBook}</span>
                <span class="chapter-num">Chapter ${this.currentChapter}</span>
            </div>
            <div class="verses">${backContent}</div>
        `;
        
        turningPage.style.transform = 'rotateY(-180deg)';
        turningPage.classList.add('turning-backward');
        
        setTimeout(() => {
            this.currentPage -= 2;
            this.renderCurrentPages();
            this.updateNavigation();
            turningPage.classList.remove('turning-backward');
            turningPage.style.transform = '';
            this.isAnimating = false;
        }, 800);
    }
    
    setFontSize(size) {
        this.fontSize = size;
        // Apply to reader view
        const readerView = document.getElementById('readerView');
        readerView.classList.remove('font-small', 'font-medium', 'font-large', 'font-xlarge');
        readerView.classList.add(`font-${size}`);
        
        // Apply to video view (Watch & Listen)
        const videoView = document.getElementById('videoView');
        videoView.classList.remove('font-small', 'font-medium', 'font-large', 'font-xlarge');
        videoView.classList.add(`font-${size}`);
        
        // Apply to parallel view
        const parallelView = document.getElementById('parallelView');
        parallelView.classList.remove('font-small', 'font-medium', 'font-large', 'font-xlarge');
        parallelView.classList.add(`font-${size}`);
    }
    
    // ===== Parallel Translation View =====
    
    // Update translation dropdowns: both selects show ALL translations.
    // Either side can host Hebrew (or any other translation).
    updateTranslationOptions() {
        const trans1Select = document.getElementById('parallelTrans1');
        const trans2Select = document.getElementById('parallelTrans2');
        if (!trans1Select || !trans2Select) return;

        if (this.allTranslations.length === 0) {
            this.allTranslations = Array.from(trans1Select.options).map(option => ({
                value: option.value,
                text: option.text
            }));
        }

        const populate = (select, currentValue) => {
            select.innerHTML = '';
            this.allTranslations.forEach(trans => {
                const option = document.createElement('option');
                option.value = trans.value;
                option.text = trans.text;
                if (trans.value === currentValue) option.selected = true;
                select.appendChild(option);
            });
        };
        populate(trans1Select, this.parallelTrans1);
        populate(trans2Select, this.parallelTrans2);
    }
    
    // Sync view: both selects show ALL translations.
    updateSyncTranslationOptions() {
        const syncTrans1Select = document.getElementById('syncTrans1');
        const syncTrans2Select = document.getElementById('syncTrans2');
        if (!syncTrans1Select) return;

        if (this.allTranslations.length === 0) {
            this.allTranslations = Array.from(syncTrans1Select.options).map(option => ({
                value: option.value,
                text: option.text
            }));
        }

        const populate = (select, currentValue) => {
            if (!select) return;
            select.innerHTML = '';
            this.allTranslations.forEach(trans => {
                const option = document.createElement('option');
                option.value = trans.value;
                option.text = trans.text;
                if (trans.value === currentValue) option.selected = true;
                select.appendChild(option);
            });
        };
        populate(syncTrans1Select, this.syncTrans1);
        populate(syncTrans2Select, this.syncTrans2);
    }
    
    async loadParallelVerses() {
        try {
            const reqId = ++this._parallelReqId;
            const response = await fetch(
                `/api/verses/parallel/${this.currentBook}/${this.currentChapter}?translation1=${this.parallelTrans1}&translation2=${this.parallelTrans2}`
            );
            const data = await response.json();
            if (reqId !== this._parallelReqId) return;

            this.parallelVerses1 = data.translation1.verses;
            this.parallelVerses2 = data.translation2.verses;
            
            // Update header with actual translation (shows fallback if applicable)
            document.getElementById('parallelBookChapter').textContent = `${this.currentBook} ${this.currentChapter}`;
            
            // Hide column entirely when its translation has no equivalent for
            // this book (fell back to a different translation). Show only the
            // column whose translation actually has the passage.
            const col1 = document.getElementById('parallelCol1');
            const col2 = document.getElementById('parallelCol2');
            const fb1 = !!data.translation1.fallback;
            const fb2 = !!data.translation2.fallback;
            if (col1 && col2) {
                col1.classList.toggle('hidden-column', fb1 && !fb2);
                col2.classList.toggle('hidden-column', fb2 && !fb1);
                const wrap = col1.parentElement;
                if (wrap) wrap.classList.toggle('single-column', (fb1 && !fb2) || (fb2 && !fb1));
            }

            // Show actual translation name, with fallback indicator if needed
            const trans1Label = data.translation1.fallback 
                ? `${this.parallelTrans1} → ${data.translation1.actual}` 
                : this.parallelTrans1;
            const trans2Label = data.translation2.fallback 
                ? `${this.parallelTrans2} → ${data.translation2.actual}` 
                : this.parallelTrans2;
            
            document.getElementById('col1TransName').textContent = trans1Label;
            document.getElementById('col2TransName').textContent = trans2Label;
            
            // Show toast only when BOTH columns fell back (nothing useful to display)
            if (fb1 && fb2) {
                this.showToast(`${this.parallelTrans1} and ${this.parallelTrans2} not available. Showing NIV fallback.`, 'info');
            }
            
            // Render columns
            this.renderParallelColumn('col1Verses', this.parallelVerses1);
            this.renderParallelColumn('col2Verses', this.parallelVerses2);
            
            // Add synchronized scrolling
            this.setupSyncScroll();
            
        } catch (error) {
            console.error('Failed to load parallel verses:', error);
            this.showToast('Failed to load translations', 'error');
        }
    }
    
    renderParallelColumn(elementId, verses) {
        const container = document.getElementById(elementId);
        const verseNums = Object.keys(verses).map(Number).sort((a, b) => a - b);
        const HEB = /[\u0590-\u05FF]/;

        container.innerHTML = verseNums.map(num => {
            const text = verses[num] || '';
            const body = text.split(' ').map(w => HEB.test(w)
                ? this._wrapHebrewToken(w)
                : this._wrapWordToken(w)
            ).join(' ');
            return `
            <div class="parallel-verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                <span class="verse-text">${body}</span>
            </div>
        `;
        }).join('');
        
        // Add click handlers for verse highlighting
        container.querySelectorAll('.parallel-verse').forEach(verse => {
            verse.addEventListener('click', () => {
                const verseNum = verse.dataset.verse;
                this.highlightParallelVerse(verseNum);
            });
        });
    }
    
    highlightParallelVerse(verseNum) {
        // Remove previous highlights
        document.querySelectorAll('.parallel-verse.active').forEach(v => v.classList.remove('active'));
        
        // Highlight matching verses in both columns
        document.querySelectorAll(`.parallel-verse[data-verse="${verseNum}"]`).forEach(v => {
            v.classList.add('active');
            v.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    }
    
    setupSyncScroll() {
        const col1 = document.getElementById('col1Verses');
        const col2 = document.getElementById('col2Verses');
        if (!col1 || !col2) return;
        // Attach listeners only once. Verse nodes are recreated on each
        // chapter change but the container element persists, so we
        // don't leak handlers.
        if (this._parallelScrollWired) return;
        this._parallelScrollWired = true;
        let suppress = 0;
        const findAnchor = (container) => {
            const verses = container.querySelectorAll('.parallel-verse, .sync-verse');
            const cTop = container.getBoundingClientRect().top;
            let best = null;
            for (const v of verses) {
                const top = v.getBoundingClientRect().top;
                if (top >= cTop - 4) { best = best || v; }
                if (top >= cTop + 8) break;
                best = v;
            }
            if (!best) return null;
            return { verse: best.dataset.verse, offset: best.getBoundingClientRect().top - cTop };
        };
        const mirror = (source, target) => {
            if (suppress) return;
            const anchor = findAnchor(source);
            if (!anchor || anchor.verse == null) return;
            const match = target.querySelector(`[data-verse="${anchor.verse}"]`);
            if (!match) return;
            const tTop = target.getBoundingClientRect().top;
            const desired = match.getBoundingClientRect().top - tTop;
            const delta = desired - anchor.offset;
            if (Math.abs(delta) < 1) return;
            suppress++;
            target.scrollTop += delta;
            requestAnimationFrame(() => {
                requestAnimationFrame(() => { suppress = Math.max(0, suppress - 1); });
            });
        };
        col1.addEventListener('scroll', () => mirror(col1, col2), { passive: true });
        col2.addEventListener('scroll', () => mirror(col2, col1), { passive: true });
    }
    
    // ===== Video Sync =====
    async loadVideoSync() {
        try {
            // Ensure sync translation options are properly filtered
            this.updateSyncTranslationOptions();
            
            // Reset sync tracking for new chapter
            this.lastHighlightedVerse = null;
            this.verseStartTimes.clear();
            this.recentVerseMatches = [];
            this.verseIndex = null;
            
            const response = await fetch(`/api/sync/${this.currentBook}/${this.currentChapter}`);
            this.syncData = await response.json();
            
            document.getElementById('syncBookChapter').textContent = `${this.currentBook} ${this.currentChapter}`;
            document.getElementById('syncColName1').textContent = this.syncTrans1;
            document.getElementById('syncColName2').textContent = this.syncTrans2;
            
            if (this.syncData.video_id || this.syncData.playlist_id) {
                const videoId = this.syncData.video_id || null;
                const playlistId = this.syncData.playlist_id || null;
                const playlistIndex = this.syncData.playlist_index || 0;
                this.captions = null;
                this.lastCaptionVideoId = null;
                this.currentCaptionIndex = -1;
                this.lastCaptionText = null;
                
                // If we have an explicit video_id, load it directly for best caption support
                // Otherwise fall back to playlist-based loading
                if (videoId && videoId !== 'placeholder_video_id') {
                    this.initYouTubePlayer(videoId, null, 0);
                } else if (playlistId) {
                    this.initYouTubePlayer(null, playlistId, playlistIndex);
                }
                
                this.renderSyncText();
                document.querySelector('.video-placeholder').style.display = 'none';
                const _vBtn = document.getElementById('videoToggleBtn');
                if (_vBtn) _vBtn.style.display = '';
                
                // Fetch dynamic captions from YouTube for verse sync
                if (videoId && videoId !== 'placeholder_video_id') {
                    this.fetchCaptions(videoId);
                }
                
                console.log(`Loading video: ${videoId || 'playlist'}, playlist: ${playlistId}, index: ${playlistIndex}`);
            } else {
                // No video for this chapter: hide the placeholder AND the
                // video toggle button silently — no need to notify the user.
                document.querySelector('.video-placeholder').style.display = 'none';
                const videoWrapper = document.querySelector('.video-player-wrapper');
                if (videoWrapper) {
                    videoWrapper.classList.remove('visible-player');
                    videoWrapper.classList.add('hidden-player');
                }
                const vBtn = document.getElementById('videoToggleBtn');
                if (vBtn) {
                    vBtn.style.display = 'none';
                    vBtn.classList.remove('active');
                }
                document.getElementById('syncStatusText').textContent = '';
                this.renderSyncTextNoVideo();
            }
        } catch (error) {
            console.error('Failed to load sync data:', error);
        }
    }
    
    async renderSyncText() {
        // Fetch both translations for sync view
        const reqId = ++this._syncReqId;
        const [response1, response2] = await Promise.all([
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans1}`),
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans2}`)
        ]);
        
        const data1 = await response1.json();
        const data2 = await response2.json();
        if (reqId !== this._syncReqId) return;
        
        // Handle new response format
        const verses1 = data1.verses || data1;
        const verses2 = data2.verses || data2;
        
        const syncVerses1 = document.getElementById('syncVerses1');
        const syncVerses2 = document.getElementById('syncVerses2');
        
        // Update column headers with actual translation (shows fallback if applicable)
        const trans1Label = data1.fallback 
            ? `${this.syncTrans1} → ${data1.translation}` 
            : this.syncTrans1;
        const trans2Label = data2.fallback 
            ? `${this.syncTrans2} → ${data2.translation}` 
            : this.syncTrans2;
        
        document.getElementById('syncColName1').textContent = trans1Label;
        document.getElementById('syncColName2').textContent = trans2Label;
        this.applySyncColumnVisibility(!!data1.fallback, !!data2.fallback);
        
        // Render first translation with word highlighting
        syncVerses1.innerHTML = this.renderSyncVerses(verses1, true);
        
        // Render second translation 
        syncVerses2.innerHTML = this.renderSyncVerses(verses2, false);
        
        // Build the searchable verse index used by caption matching
        this.buildVerseIndex(verses1);

        // Setup synchronized scrolling between sync columns
        this.setupSyncColumnScroll();

        // Apply per-verse highlights/notes/bookmarks to the freshly
        // rendered DOM so they're visible immediately on every render.
        this._applyVerseAnnotations();

        // If TTS is currently playing, the queue is now stale (it was
        // built from the previous translation/lang). Restart it from the
        // current verse so the new column's language is used.
        this.restartTTSIfPlaying();
    }
    
    renderSyncVerses(verses, withWordSync) {
        const verseNums = Object.keys(verses).map(Number).sort((a, b) => a - b);
        const HEB = /[\u0590-\u05FF]/;

        return verseNums.map(verseNum => {
            const verseText = verses[verseNum];

            // Always wrap words in spans for dynamic highlighting.
            // Hebrew words additionally get the .heb-word class so they
            // can be tapped to look up an English gloss; non-Hebrew
            // words get .bw-word so they can be tapped for the generic
            // word-study popover (count occurrences / pronounce).
            const words = verseText.split(' ');
            const wordSpans = words.map((word) => {
                if (HEB.test(word)) return this._wrapHebrewToken(word, 'sync-word');
                return this._wrapWordToken(word, 'sync-word');
            }).join(' ');

            return `
                <p class="sync-verse" data-verse="${verseNum}">
                    <span class="verse-num">${verseNum}</span>
                    ${wordSpans}
                </p>
            `;
        }).join('');
    }
    
    async renderSyncTextNoVideo() {
        // Fetch both translations for display without video
        const [response1, response2] = await Promise.all([
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans1}`),
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans2}`)
        ]);
        
        const data1 = await response1.json();
        const data2 = await response2.json();
        
        // Handle new response format
        const verses1 = data1.verses || data1;
        const verses2 = data2.verses || data2;
        
        // Update column headers with actual translation (shows fallback if applicable)
        const trans1Label = data1.fallback 
            ? `${this.syncTrans1} → ${data1.translation}` 
            : this.syncTrans1;
        const trans2Label = data2.fallback 
            ? `${this.syncTrans2} → ${data2.translation}` 
            : this.syncTrans2;
        
        document.getElementById('syncColName1').textContent = trans1Label;
        document.getElementById('syncColName2').textContent = trans2Label;
        this.applySyncColumnVisibility(!!data1.fallback, !!data2.fallback);
        
        const syncVerses1 = document.getElementById('syncVerses1');
        const syncVerses2 = document.getElementById('syncVerses2');
        
        syncVerses1.innerHTML = this.renderSimpleVerses(verses1);
        syncVerses2.innerHTML = this.renderSimpleVerses(verses2);
        
        this.setupSyncColumnScroll();
    }
    
    renderSimpleVerses(verses) {
        const verseNums = Object.keys(verses).map(Number).sort((a, b) => a - b);
        const HEB = /[\u0590-\u05FF]/;

        return verseNums.map(num => {
            const text = verses[num] || '';
            // Wrap each word so individual words are tappable —
            // Hebrew gets .heb-word (dictionary lookup); everything
            // else gets .bw-word (count occurrences / pronounce).
            const body = text.split(' ').map(w => HEB.test(w)
                ? this._wrapHebrewToken(w)
                : this._wrapWordToken(w)
            ).join(' ');
            return `
            <p class="sync-verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                ${body}
            </p>
        `;
        }).join('');
    }

    applySyncColumnVisibility(fb1, fb2) {
        const col1 = document.getElementById('syncCol1');
        const col2 = document.getElementById('syncCol2');
        if (!col1 || !col2) return;
        // Remember last fallback state so the Hebrew toggle can re-apply
        // visibility without forgetting an active fallback.
        if (typeof fb1 === 'boolean') this._lastFb1 = fb1;
        if (typeof fb2 === 'boolean') this._lastFb2 = fb2;
        const f1 = !!this._lastFb1;
        const f2 = !!this._lastFb2;
        // User-toggled "hide Hebrew" forces col2 hidden regardless of fallback.
        const userHideRight = !!this.hebrewDisabled;
        const hide1 = f1 && !f2 && !userHideRight;
        const hide2 = (f2 && !f1) || userHideRight;
        col1.classList.toggle('hidden-column', hide1);
        col2.classList.toggle('hidden-column', hide2);
        const wrap = col1.parentElement;
        if (wrap) wrap.classList.toggle('single-column', hide1 || hide2);
        this.updateSyncRoleBadges();
    }

    // Show "Read aloud" badge on whichever sync column is the actual TTS
    // source, and "Follow along" on the other. Hide both when only one
    // column is visible (the badge would be redundant).
    updateSyncRoleBadges() {
        const role1 = document.getElementById('syncRole1');
        const role2 = document.getElementById('syncRole2');
        if (!role1 || !role2) return;
        const col1 = document.getElementById('syncCol1');
        const col2 = document.getElementById('syncCol2');
        const col1Hidden = col1 && col1.classList.contains('hidden-column');
        const col2Hidden = (col2 && col2.classList.contains('hidden-column')) || !!this.hebrewDisabled;
        const onlyOne = col1Hidden || col2Hidden;
        // Right column is the default audio source; if it's hidden, left becomes the source.
        const rightIsSource = !col2Hidden;
        const setBadge = (el, isSource, isSourceLabel) => {
            el.classList.toggle('primary', isSource);
            el.style.display = onlyOne ? 'none' : '';
            const label = isSource ? 'Read aloud' : 'Follow along';
            // Replace just the trailing text node (keep the SVG)
            let textNode = null;
            for (const n of el.childNodes) {
                if (n.nodeType === Node.TEXT_NODE && n.textContent.trim()) { textNode = n; break; }
            }
            if (textNode) textNode.textContent = ' ' + label;
            else el.appendChild(document.createTextNode(' ' + label));
            el.title = isSource
                ? 'Audio is being read from this column'
                : 'This column follows along with what is being read';
        };
        setBadge(role1, !rightIsSource, true);
        setBadge(role2, rightIsSource,  true);
    }
    
    // Returns true while audio narration is actively driving the page
    // (TTS speaking, or the YouTube player in PLAYING state). When this
    // is false the two sync columns scroll independently.
    _isLiveReadingActive() {
        if (this.ttsState === 'playing') return true;
        try {
            if (this.player && this.isPlayerReady &&
                typeof YT !== 'undefined' && YT.PlayerState &&
                this.player.getPlayerState() === YT.PlayerState.PLAYING) {
                return true;
            }
        } catch { /* player may not be ready */ }
        return false;
    }

    setupSyncColumnScroll() {
        const col1 = document.getElementById('syncVerses1');
        const col2 = document.getElementById('syncVerses2');
        if (!col1 || !col2) return;
        // Attach listeners only once per column. On re-render the verse
        // nodes are recreated but the container element is the same, so
        // listeners keep working without leaking.
        if (this._syncScrollWired) return;
        this._syncScrollWired = true;

        // Programmatic scrolls (the sync mirror, scrollIntoView from the
        // active-verse highlighter, etc.) set this flag so the resulting
        // 'scroll' event is not treated as user input and does not
        // bounce back to the source column.
        let suppress = 0;

        // Find the verse number anchored at the top of `container` and
        // how far past the top it is, so we can place the matching verse
        // in the other column at the same offset.
        const findAnchorVerse = (container) => {
            const verses = container.querySelectorAll('.sync-verse');
            const cTop = container.getBoundingClientRect().top;
            let best = null;
            for (const v of verses) {
                const top = v.getBoundingClientRect().top;
                // The first verse whose top is at-or-below the container
                // top is our anchor; the previous one (still partially
                // visible above) is acceptable too.
                if (top >= cTop - 4) { best = best || v; }
                if (top >= cTop + 8) break;
                best = v;
            }
            if (!best) return null;
            return {
                verse: best.dataset.verse,
                offset: best.getBoundingClientRect().top - cTop,
            };
        };

        const mirror = (source, target) => {
            if (suppress) return;
            // Independent scrolling unless "live reading" is active —
            // i.e. TTS is currently speaking, or the YouTube player is
            // actively playing audio. When idle/paused, let each column
            // scroll freely so the reader can browse on their own.
            if (!this._isLiveReadingActive()) return;
            const anchor = findAnchorVerse(source);
            if (!anchor) return;
            const match = target.querySelector(`.sync-verse[data-verse="${anchor.verse}"]`);
            if (!match) return;
            const tTop = target.getBoundingClientRect().top;
            const desired = match.getBoundingClientRect().top - tTop;
            const delta = desired - anchor.offset;
            if (Math.abs(delta) < 1) return;
            suppress++;
            target.scrollTop += delta;
            // Release on next frame so the resulting scroll event is
            // swallowed before user input can fire again.
            requestAnimationFrame(() => {
                requestAnimationFrame(() => { suppress = Math.max(0, suppress - 1); });
            });
        };

        col1.addEventListener('scroll', () => mirror(col1, col2), { passive: true });
        col2.addEventListener('scroll', () => mirror(col2, col1), { passive: true });

        // Expose so other code (e.g. active-verse highlighter) can mark
        // a programmatic scroll without triggering a mirror loop.
        // The optional `holdMs` keeps suppression alive long enough for
        // a smooth-scroll animation to settle.
        this._suppressSyncScroll = (fn, holdMs) => {
            suppress++;
            try { fn(); } finally {
                const release = () => { suppress = Math.max(0, suppress - 1); };
                if (holdMs && holdMs > 0) {
                    setTimeout(release, holdMs);
                } else {
                    requestAnimationFrame(() => requestAnimationFrame(release));
                }
            }
        };
    }
    
    initYouTubePlayer(videoId, playlistId = null, playlistIndex = 0) {
        // If player exists, load new video or playlist
        if (this.player && this.isPlayerReady) {
            if (playlistId) {
                this.player.cuePlaylist({
                    list: playlistId,
                    listType: 'playlist',
                    index: playlistIndex
                });
                // Only auto-play if not navigating from search
                if (!this.suppressAutoPlay) {
                    setTimeout(() => {
                        if (this.player) {
                            this.player.playVideoAt(playlistIndex);
                        }
                    }, 500);
                }
            } else if (videoId) {
                if (this.suppressAutoPlay) {
                    this.player.cueVideoById(videoId);
                } else {
                    this.player.loadVideoById(videoId);
                }
            }
            this.suppressAutoPlay = false;
            return;
        }
        
        // Wait for YouTube API to load
        if (typeof YT === 'undefined' || !YT.Player) {
            setTimeout(() => this.initYouTubePlayer(videoId, playlistId, playlistIndex), 100);
            return;
        }
        
        // Build player vars - support both single video and playlist mode
        const playerVars = {
            'playsinline': 1,
            'controls': 1,  // Enable controls for playlist navigation
            'modestbranding': 1,
            'rel': 0,
            'autoplay': this.suppressAutoPlay ? 0 : 1
        };
        // Clear the flag after using it for new player creation
        if (this.suppressAutoPlay) this.suppressAutoPlay = false;
        
        // If playlist ID provided, use playlist mode
        if (playlistId) {
            playerVars.list = playlistId;
            playerVars.listType = 'playlist';
            playerVars.index = playlistIndex;
        }
        
        // Build player options
        const playerOptions = {
            height: '100%',
            width: '100%',
            playerVars: playerVars,
            events: {
                'onReady': () => {
                    this.isPlayerReady = true;
                    this.updateTimeDisplay();
                    // Apply user-selected playback rate (if supported)
                    try { this.setPlaybackRate(this.playbackRate); } catch (err) { /* ignore */ }
                    this.fetchCaptionsForCurrentVideo();
                },
                'onStateChange': (e) => this.onPlayerStateChange(e),
                'onApiChange': () => this.fetchCaptionsForCurrentVideo()
            }
        };
        
        // Only add videoId if we have one and not using playlist
        if (videoId && !playlistId) {
            playerOptions.videoId = videoId;
        }
        
        this.player = new YT.Player('youtubePlayer', playerOptions);
    }
    
    onPlayerStateChange(event) {
        const playBtn = document.getElementById('playPauseBtn');

        if (
            event.data === YT.PlayerState.PLAYING ||
            event.data === YT.PlayerState.CUED
        ) {
            this.fetchCaptionsForCurrentVideo();
        }
        
        if (event.data === YT.PlayerState.PLAYING) {
            playBtn.classList.add('playing');
            document.querySelector('.sync-indicator').classList.add('active');
            document.getElementById('syncStatusText').textContent = 'Syncing...';
            this.startSyncInterval();
        } else if (event.data === YT.PlayerState.PAUSED || event.data === YT.PlayerState.ENDED) {
            playBtn.classList.remove('playing');
            document.querySelector('.sync-indicator').classList.remove('active');
            document.getElementById('syncStatusText').textContent = 'Paused';
            this.stopSyncInterval();
            
            // Do one sync update when paused to show correct position
            if (event.data === YT.PlayerState.PAUSED && this.player) {
                const currentTime = this.player.getCurrentTime();
                const duration = this.player.getDuration();
                this.syncWithCaptions(currentTime, duration);
            }

            // Auto-continue to the next chapter when the video ends.
            if (event.data === YT.PlayerState.ENDED && this.autoAdvanceChapter) {
                const sel = document.getElementById('chapterSelect');
                const maxChapter = sel ? sel.options.length : 0;
                if (this.currentChapter < maxChapter) {
                    this._autoplayAfterLoad = true;
                    this.nextChapter();
                }
            }
        }
    }
    
    togglePlay() {
        // If the user has disabled the Hebrew column, the (Hebrew-narrated)
        // video isn't useful — drive TTS for the left translation instead.
        if (this.hebrewDisabled) {
            this.toggleTTS();
            return;
        }
        // If no YouTube player is ready (no video for this chapter), fall
        // back to browser TTS using the same play button.
        if (!this.player || !this.isPlayerReady) {
            this.toggleTTS();
            return;
        }
        this.clearSearchHighlight();
        
        const state = this.player.getPlayerState();
        if (state === YT.PlayerState.PLAYING) {
            this.player.pauseVideo();
        } else {
            this.player.playVideo();
        }
    }

    // ===== Browser Text-to-Speech (used when no video is available) =====
    // Uses window.speechSynthesis. Reads the chapter verse-by-verse in the
    // appropriate language, highlights the active verse, and updates the
    // existing progress bar / time display / play button.
    ttsLangFor(translationName) {
        const t = (translationName || '').toLowerCase();
        if (t.includes('hungarian')) return 'hu-HU';
        if (t.includes('hebrew'))    return 'he-IL';
        return 'en-US';
    }

    // Languages whose browser TTS engines are unreliable enough that we
    // should always go straight to the server gTTS path. Hebrew in
    // particular tends to crash silently (or fall back to an English voice
    // spelling out characters) in Chrome/Safari when nikud/cantillation
    // marks are present.
    ttsShouldForceServer(lang) {
        // User override: always use the online voice.
        if (this.ttsSettings && this.ttsSettings.preferServer) return true;
        const base = (lang || '').toLowerCase().split('-')[0];
        return base === 'he' || base === 'ar' || base === 'yi';
    }

    pickTTSVoice(lang) {
        const voices = window.speechSynthesis.getVoices() || [];
        if (!voices.length) return null;
        const want = (lang || '').toLowerCase();
        const base = want.split('-')[0];
        // 0. user-chosen voice (per language) wins if it's still installed
        const userPick = (this.ttsSettings && this.ttsSettings.voice && this.ttsSettings.voice[base]) || '';
        if (userPick) {
            const u = voices.find(x => x.voiceURI === userPick || x.name === userPick);
            if (u) return u;
        }
        // 1. exact match (e.g. hu-HU)
        let v = voices.find(x => (x.lang || '').toLowerCase() === want);
        // 2. same base lang and 'default' flag preferred (e.g. hu-*)
        if (!v) v = voices.find(x => (x.lang || '').toLowerCase().startsWith(base + '-') && x.default);
        // 3. any voice in same base lang
        if (!v) v = voices.find(x => (x.lang || '').toLowerCase().startsWith(base + '-'));
        // 4. base-only lang code (e.g. "hu")
        if (!v) v = voices.find(x => (x.lang || '').toLowerCase() === base);
        return v || null;
    }

    waitForVoices(timeoutMs = 1500) {
        return new Promise(resolve => {
            const got = window.speechSynthesis.getVoices();
            if (got && got.length) return resolve(got);
            let done = false;
            const onChange = () => {
                if (done) return;
                done = true;
                window.speechSynthesis.removeEventListener('voiceschanged', onChange);
                resolve(window.speechSynthesis.getVoices() || []);
            };
            window.speechSynthesis.addEventListener('voiceschanged', onChange);
            setTimeout(() => {
                if (done) return;
                done = true;
                window.speechSynthesis.removeEventListener('voiceschanged', onChange);
                resolve(window.speechSynthesis.getVoices() || []);
            }, timeoutMs);
        });
    }

    // ===== Voice settings dialog =====
    saveTTSSettings() {
        try { localStorage.setItem('ttsSettings', JSON.stringify(this.ttsSettings)); } catch {}
    }

    bindTTSSettings() {
        const btn      = document.getElementById('ttsSettingsBtn');
        const overlay  = document.getElementById('ttsSettingsOverlay');
        if (!btn || !overlay) return;
        const closeBtn = document.getElementById('ttsSettingsClose');
        const testBtn  = document.getElementById('ttsTestBtn');
        const resetBtn = document.getElementById('ttsResetBtn');
        const preferEl = document.getElementById('ttsPreferServer');

        const open = async () => {
            await this.populateVoiceSettings();
            overlay.classList.add('active');
            overlay.setAttribute('aria-hidden', 'false');
            document.body.classList.add('modal-open');
        };
        const close = () => {
            overlay.classList.remove('active');
            overlay.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('modal-open');
        };

        btn.addEventListener('click', open);
        closeBtn?.addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('active')) close();
        });

        // Browser (offline) voice selectors.
        ['ttsVoiceEn', 'ttsVoiceHu', 'ttsVoiceHe'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => {
                const lang = id.slice(-2).toLowerCase();
                this.ttsSettings.voice[lang] = el.value || '';
                this.saveTTSSettings();
            });
        });
        // Online (neural) voice selectors.
        ['ttsOnlineVoiceEn', 'ttsOnlineVoiceHu', 'ttsOnlineVoiceHe'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => {
                const lang = id.slice(-2).toLowerCase();
                this.ttsSettings.onlineVoice[lang] = el.value || '';
                this.saveTTSSettings();
            });
        });
        preferEl?.addEventListener('change', () => {
            this.ttsSettings.preferServer = !!preferEl.checked;
            this.saveTTSSettings();
        });

        testBtn?.addEventListener('click', () => this.testTTSVoice());

        resetBtn?.addEventListener('click', () => {
            this.ttsSettings = {
                voice:       { en: '', hu: '', he: '' },
                onlineVoice: { en: '', hu: '', he: '' },
                preferServer: true,
                tld: 'com',
            };
            this.saveTTSSettings();
            this.populateVoiceSettings();
            this.showToast('Voice settings reset', 'info');
        });
    }

    // ===== Hebrew word lookup popover =====
    // Click/tap any Hebrew word in a verse to see its English gloss and a
    // short list of related (same-root) words for comparison.
    bindHebrewWordLookup() {
        // Single delegated handler so it works for words rendered later.
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (!(target instanceof HTMLElement)) return;
            // Close popover when clicking outside it (and not on a heb-word).
            if (this._hebPopover && !this._hebPopover.contains(target)
                && !target.classList.contains('heb-word')) {
                this.closeHebrewPopover();
            }
            if (target.classList.contains('heb-word')) {
                e.stopPropagation();
                this.openHebrewPopover(target);
            }
        }, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._hebPopover) this.closeHebrewPopover();
        });
        window.addEventListener('scroll', (e) => {
            // Don't dismiss when the scroll happens INSIDE the popover
            // itself (e.g. scrolling the occurrences list).
            if (this._hebPopover && e.target instanceof Node
                && this._hebPopover.contains(e.target)) return;
            this.closeHebrewPopover();
        }, true);
        window.addEventListener('resize', () => this.closeHebrewPopover());
    }

    async _fetchHebrewDictionary() {
        if (this._hebDictCache) return this._hebDictCache;
        try {
            const r = await fetch('/api/hebrew/dictionary');
            if (!r.ok) return {};
            this._hebDictCache = await r.json();
        } catch (e) {
            console.warn('Failed to load Hebrew dictionary', e);
            this._hebDictCache = {};
        }
        // Pre-build a normalized (consonant-only) index for fuzzy lookup
        // and "compare" suggestions.
        const stripMarks = (s) => (s || '').replace(/[\u0591-\u05C7]/g, '').replace(/\u05BE/g, ' ').trim();
        this._hebDictNorm = {};
        for (const [k, v] of Object.entries(this._hebDictCache)) {
            const nk = stripMarks(k);
            if (nk && !this._hebDictNorm[nk]) this._hebDictNorm[nk] = { key: k, gloss: v };
        }
        this._hebStripMarks = stripMarks;
        return this._hebDictCache;
    }

    closeHebrewPopover() {
        if (this._hebPopover) {
            this._hebPopover.remove();
            this._hebPopover = null;
        }
    }

    async openHebrewPopover(wordEl) {
        const raw = (wordEl.textContent || '').trim();
        // Strip surrounding punctuation including Hebrew sof-pasuq (׃),
        // gershayim (״), geresh (׳), maqaf (־), and the usual ASCII set.
        const word = raw.replace(/^[\s,.;:!?\u05BE\u05C0-\u05C7\u05F3\u05F4"'()\[\]{}\u00B7]+|[\s,.;:!?\u05BE\u05C0-\u05C7\u05F3\u05F4"'()\[\]{}\u00B7]+$/g, '');
        if (!word) return;

        this.closeHebrewPopover();

        // Build the popover shell immediately so the user gets feedback.
        const pop = document.createElement('div');
        pop.className = 'heb-popover';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', 'Hebrew word definition');
        pop.innerHTML = `
            <button class="heb-popover-close" aria-label="Close">×</button>
            <div class="heb-popover-word" dir="rtl" lang="he">${word}</div>
            <div class="heb-popover-gloss heb-popover-loading">Looking up…</div>
            <div class="heb-popover-related"></div>
            <div class="heb-popover-occurrences"></div>
            <div class="heb-popover-foot">
                <button type="button" class="heb-action heb-action-speak" aria-label="Hear pronunciation" title="Hear pronunciation">
                    <span class="heb-action-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                        </svg>
                    </span>
                    <span class="heb-action-label">Pronounce</span>
                </button>
                <button type="button" class="heb-action heb-action-count" aria-label="Count occurrences across the Hebrew Bible" title="Count occurrences across the Hebrew Bible">
                    <span class="heb-action-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="4"  y1="9"  x2="20" y2="9"></line>
                            <line x1="4"  y1="15" x2="20" y2="15"></line>
                            <line x1="10" y1="3"  x2="8"  y2="21"></line>
                            <line x1="16" y1="3"  x2="14" y2="21"></line>
                        </svg>
                    </span>
                    <span class="heb-action-label">Count occurrences</span>
                </button>
            </div>
        `;
        document.body.appendChild(pop);
        this._hebPopover = pop;
        pop.querySelector('.heb-popover-close').addEventListener('click', () => this.closeHebrewPopover());
        pop.addEventListener('click', (e) => e.stopPropagation());

        // Pronunciation is intentionally restricted to the right-side
        // study column so the primary reading column stays distraction-free.
        if (!this._isRightSideContainer(wordEl)) {
            pop.querySelector('.heb-action-speak')?.remove();
        }

        // Wire up the pronounce + count actions. They use the original
        // (pointed) Hebrew word so the TTS engine can apply nikud and the
        // count endpoint can normalize on its own side.
        pop.querySelector('.heb-action-speak')
            ?.addEventListener('click', () => this._speakHebrewWord(word, pop));
        pop.querySelector('.heb-action-count')
            .addEventListener('click', () => this._countHebrewOccurrences(word, pop));

        this._positionHebrewPopover(wordEl, pop);

        // Mark the active word so it's visually linked to the popover.
        document.querySelectorAll('.heb-word.active').forEach(n => n.classList.remove('active'));
        wordEl.classList.add('active');

        // Load dictionary (cached) and resolve gloss locally; fall back to
        // server endpoint if local lookup misses (e.g. dict updated server-side).
        const dict = await this._fetchHebrewDictionary();
        if (this._hebPopover !== pop) return; // user dismissed
        const stripMarks = this._hebStripMarks;
        const normWord = stripMarks(word);

        let matched = null, gloss = null;
        if (dict[word]) { matched = word; gloss = dict[word]; }
        else if (this._hebDictNorm[normWord]) {
            matched = this._hebDictNorm[normWord].key;
            gloss   = this._hebDictNorm[normWord].gloss;
        } else {
            try {
                const r = await fetch(`/api/hebrew/define?word=${encodeURIComponent(word)}`);
                if (r.ok) {
                    const j = await r.json();
                    matched = j.matched; gloss = j.gloss;
                }
            } catch {}
        }
        if (this._hebPopover !== pop) return;

        const glossEl = pop.querySelector('.heb-popover-gloss');
        glossEl.classList.remove('heb-popover-loading');
        if (gloss) {
            glossEl.innerHTML = `
                <div class="heb-gloss-text">${this._escapeHtml(gloss)}</div>
                <div class="heb-gloss-meta">
                    <span class="heb-gloss-pointed" dir="rtl" lang="he">${matched || word}</span>
                    <span class="heb-gloss-bare" dir="rtl" lang="he">${normWord}</span>
                </div>
            `;
        } else {
            glossEl.innerHTML = `
                <div class="heb-gloss-empty">No definition in the curated dictionary yet.</div>
                <div class="heb-gloss-meta">
                    <span class="heb-gloss-bare" dir="rtl" lang="he">${normWord}</span>
                </div>
            `;
        }

        // "Compare" panel: other dictionary entries whose consonant root
        // shares ≥3 contiguous letters with this word — handy for spotting
        // related verbal forms and shared roots across passages.
        const related = this._findRelatedHebrewWords(normWord, matched, 6);
        const relEl = pop.querySelector('.heb-popover-related');
        if (related.length) {
            relEl.innerHTML = `
                <div class="heb-related-title">Compare</div>
                <ul class="heb-related-list">
                    ${related.map(r => `
                        <li>
                            <button type="button" class="heb-related-item" data-word="${this._escapeHtml(r.key)}">
                                <span class="heb-related-word" dir="rtl" lang="he">${this._escapeHtml(r.key)}</span>
                                <span class="heb-related-gloss">${this._escapeHtml(r.gloss)}</span>
                            </button>
                        </li>
                    `).join('')}
                </ul>
            `;
            relEl.querySelectorAll('.heb-related-item').forEach(btn => {
                btn.addEventListener('click', () => {
                    const w = btn.dataset.word;
                    // Re-open popover anchored to the same word in the page.
                    const fake = document.createElement('span');
                    fake.className = 'heb-word';
                    fake.textContent = w;
                    fake.style.position = 'absolute';
                    const r = wordEl.getBoundingClientRect();
                    fake.style.left = (r.left + window.scrollX) + 'px';
                    fake.style.top  = (r.top  + window.scrollY) + 'px';
                    document.body.appendChild(fake);
                    this.openHebrewPopover(fake);
                    setTimeout(() => fake.remove(), 0);
                });
            });
        }

        this._positionHebrewPopover(wordEl, pop);
    }

    _findRelatedHebrewWords(normWord, exclude, limit) {
        if (!normWord || !this._hebDictNorm) return [];
        const out = [];
        for (const [nk, info] of Object.entries(this._hebDictNorm)) {
            if (info.key === exclude) continue;
            // Score by length of longest shared substring.
            const score = this._longestCommonSubstring(normWord, nk);
            if (score >= 3) out.push({ key: info.key, gloss: info.gloss, score });
        }
        out.sort((a, b) => b.score - a.score);
        return out.slice(0, limit);
    }

    // Play a TTS pronunciation of the given Hebrew word using the existing
    // /api/tts endpoint (Edge neural Hebrew voice). Reuses a single audio
    // element so rapid taps don't stack overlapping playbacks.
    async _speakHebrewWord(word, pop) {
        if (!word) return;
        const btn = pop?.querySelector('.heb-action-speak');
        if (btn) btn.classList.add('is-loading');
        // Stop any prior playback BEFORE wiring new listeners. We mark the
        // old audio as superseded so its later 'error' / 'ended' events
        // (fired when we clear its src) don't trigger a misleading toast.
        if (this._hebAudio) {
            this._hebAudio._superseded = true;
            try { this._hebAudio.pause(); } catch {}
            try { this._hebAudio.removeAttribute('src'); this._hebAudio.load(); } catch {}
        }
        const audio = new Audio(`/api/tts?text=${encodeURIComponent(word)}&lang=he`);
        this._hebAudio = audio;
        audio.addEventListener('ended', () => {
            if (audio._superseded) return;
            if (btn) btn.classList.remove('is-playing');
        });
        // Only treat 'error' as a real failure if it fires before/during
        // playback (i.e. the audio never reached a playable state). After
        // a successful play we ignore subsequent errors triggered by src
        // clearing on the next click.
        let played = false;
        audio.addEventListener('error', () => {
            if (audio._superseded || played) return;
            if (btn) btn.classList.remove('is-loading', 'is-playing');
            this.showToast?.('Pronunciation failed', 'error');
        });
        try {
            await audio.play();
            played = true;
            if (btn) {
                btn.classList.remove('is-loading');
                btn.classList.add('is-playing');
            }
        } catch (e) {
            if (audio._superseded) return;
            if (btn) btn.classList.remove('is-loading', 'is-playing');
            this.showToast?.('Pronunciation failed', 'error');
        }
    }

    // Query the server for how many times this word appears across the
    // cached Hebrew Bible. Renders a small results panel inside the
    // popover with the totals and a few clickable sample references.
    async _countHebrewOccurrences(word, pop) {
        const target = pop?.querySelector('.heb-popover-occurrences');
        const btn = pop?.querySelector('.heb-action-count');
        if (!target || !word) return;
        target.innerHTML = `<div class="heb-occ-loading">Counting…</div>`;
        if (btn) btn.disabled = true;
        try {
            const r = await fetch(`/api/hebrew/occurrences?word=${encodeURIComponent(word)}&limit=15`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (this._hebPopover !== pop) return; // user dismissed
            if (!data.count) {
                target.innerHTML = `
                    <div class="heb-occ-summary">
                        No occurrences found in the cached Hebrew Bible (${data.corpus_size || 0} verses).
                    </div>`;
            } else {
                const samples = (data.samples || []).map(s => `
                    <li>
                        <button type="button" class="heb-occ-ref" data-book="${this._escapeHtml(s.book)}" data-chapter="${s.chapter}" data-verse="${s.verse}">
                            <span class="heb-occ-ref-label">${this._escapeHtml(s.book)} ${s.chapter}:${s.verse}</span>
                            ${s.hits > 1 ? `<span class="heb-occ-ref-hits">×${s.hits}</span>` : ''}
                        </button>
                    </li>
                `).join('');
                const more = data.verses_with_matches > (data.samples || []).length
                    ? `<div class="heb-occ-more">…and ${data.verses_with_matches - (data.samples || []).length} more verse(s).</div>`
                    : '';
                target.innerHTML = `
                    <div class="heb-occ-summary">
                        <strong>${data.count}</strong> occurrence${data.count === 1 ? '' : 's'}
                        in <strong>${data.verses_with_matches}</strong> verse${data.verses_with_matches === 1 ? '' : 's'}
                        across the Hebrew Bible.
                    </div>
                    <ul class="heb-occ-list">${samples}</ul>
                    ${more}
                `;
                target.querySelectorAll('.heb-occ-ref').forEach(ref => {
                    ref.addEventListener('click', () => {
                        const book = ref.dataset.book;
                        const chapter = parseInt(ref.dataset.chapter, 10);
                        // Jump to the verse in the current view if the
                        // reader supports it; otherwise just navigate.
                        if (typeof this.navigateToReference === 'function') {
                            this.navigateToReference(book, chapter);
                        } else {
                            this.currentBook = book;
                            this.currentChapter = chapter;
                            this.loadVerses?.();
                        }
                        this.closeHebrewPopover();
                    });
                });
            }
            // Reposition since the popover just grew.
            if (this._hebPopover === pop) {
                const anchor = document.querySelector('.heb-word.active');
                if (anchor) this._positionHebrewPopover(anchor, pop);
            }
        } catch (e) {
            target.innerHTML = `<div class="heb-occ-error">Failed to count occurrences.</div>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    _longestCommonSubstring(a, b) {
        if (!a || !b) return 0;
        let best = 0;
        const m = a.length, n = b.length;
        // Rolling 1-D DP — strings are short (a few chars) so this is cheap.
        let prev = new Array(n + 1).fill(0);
        for (let i = 1; i <= m; i++) {
            const cur = new Array(n + 1).fill(0);
            for (let j = 1; j <= n; j++) {
                if (a[i - 1] === b[j - 1]) {
                    cur[j] = prev[j - 1] + 1;
                    if (cur[j] > best) best = cur[j];
                }
            }
            prev = cur;
        }
        return best;
    }

    _escapeHtml(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    // Wrap a whitespace-delimited Hebrew token for the dictionary popover.
    // Tokens joined by maqaf (־ U+05BE) such as "בֶּן־הָאֱלֹהִים" are split into
    // separately-tappable parts so each lemma can be looked up on its own.
    // The trailing sof-pasuq (׃) and zero-width joiners are stripped from
    // the lookup key but kept visible.
    _wrapHebrewToken(word, extraClass) {
        const cls = extraClass ? `${extraClass} heb-word` : 'heb-word';
        if (!word.includes('\u05BE')) {
            return `<span class="${cls}">${this._escapeHtml(word)}</span>`;
        }
        // Split on maqaf, keep it as a visible separator outside the
        // tappable spans so the gloss applies only to the part you tap.
        const parts = word.split('\u05BE');
        return parts
            .map(p => p ? `<span class="${cls}">${this._escapeHtml(p)}</span>` : '')
            .filter(Boolean)
            .join('<span class="heb-maqaf">\u05BE</span>');
    }

    // Wrap a non-Hebrew word for the generic word-study popover.
    // Strips no characters from the visible text — punctuation is left
    // attached visually so the verse reads naturally — but the popover
    // strips it again before sending to the server.
    _wrapWordToken(word, extraClass) {
        const cls = extraClass ? `${extraClass} bw-word` : 'bw-word';
        // Skip empty, pure-punctuation, or numeric tokens.
        if (!word || !/[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]/.test(word)) {
            return extraClass
                ? `<span class="${extraClass}">${this._escapeHtml(word || '')}</span>`
                : this._escapeHtml(word || '');
        }
        return `<span class="${cls}">${this._escapeHtml(word)}</span>`;
    }

    // Right-side containers (sermon-prep "study" side). Pronunciation is
    // intentionally limited to these so the reader's primary side stays
    // distraction-free.
    _isRightSideContainer(node) {
        const RIGHT_IDS = new Set(['rightVerses', 'col2Verses', 'syncVerses2']);
        let n = node;
        while (n && n !== document.body) {
            if (n.id && RIGHT_IDS.has(n.id)) return true;
            n = n.parentElement;
        }
        return false;
    }

    // Determine which translation a word came from based on its container.
    _translationForNode(node) {
        let n = node;
        while (n && n !== document.body) {
            const id = n.id;
            if (id === 'col1Verses')   return this.parallelTrans1;
            if (id === 'col2Verses')   return this.parallelTrans2;
            if (id === 'syncVerses1')  return this.syncTrans1;
            if (id === 'syncVerses2')  return this.syncTrans2;
            if (id === 'leftVerses' || id === 'rightVerses') return this.currentTranslation;
            n = n.parentElement;
        }
        return this.currentTranslation;
    }

    // ----- Generic word popover (non-Hebrew languages) -----
    // The Hebrew popover is its own thing because it has dictionary
    // glosses and root comparisons. For every other word the user can
    // tap to count occurrences across the same translation, plus
    // (right column only) hear it pronounced via TTS.
    bindGenericWordLookup() {
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (!(target instanceof HTMLElement)) return;
            // Close on outside click.
            if (this._wordPopover && !this._wordPopover.contains(target)
                && !target.classList.contains('bw-word')) {
                this.closeWordPopover();
            }
            if (target.classList.contains('bw-word')) {
                e.stopPropagation();
                this.openWordPopover(target);
            }
        }, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._wordPopover) this.closeWordPopover();
        });
        window.addEventListener('scroll', (e) => {
            // Don't dismiss when the scroll happens inside the popover.
            if (this._wordPopover && e.target instanceof Node
                && this._wordPopover.contains(e.target)) return;
            this.closeWordPopover();
        }, true);
        window.addEventListener('resize', () => this.closeWordPopover());
    }

    closeWordPopover() {
        if (this._wordPopover) {
            this._wordPopover.remove();
            this._wordPopover = null;
        }
    }

    // Map a translation display name to a TTS BCP-47 lang code.
    _langForTranslation(translation) {
        const en = ['NIV', 'NKJV', 'KJV', 'ESV', 'NASB1995'];
        if (en.includes(translation)) return 'en';
        if (translation === 'Hungarian' || translation === 'Hungarian-Revised') return 'hu';
        if (translation === 'Hebrew') return 'he';
        return 'en';
    }

    async openWordPopover(wordEl) {
        // Clean up any other popovers first so only one is visible.
        this.closeWordPopover();
        this.closeHebrewPopover();

        const raw = (wordEl.textContent || '').trim();
        // Strip leading/trailing punctuation but preserve apostrophes
        // mid-word (e.g. don't, l'âme).
        const word = raw.replace(/^[\s\W_]+|[\s\W_]+$/gu, '');
        if (!word) return;

        const translation = this._translationForNode(wordEl);
        const lang = this._langForTranslation(translation);
        const isRight = this._isRightSideContainer(wordEl);

        const pop = document.createElement('div');
        pop.className = 'bw-popover';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', 'Word study');
        pop.innerHTML = `
            <button class="bw-popover-close" aria-label="Close">×</button>
            <div class="bw-popover-word">${this._escapeHtml(word)}</div>
            <div class="bw-popover-meta">${this._escapeHtml(translation)}</div>
            <div class="bw-popover-occurrences"></div>
            <div class="bw-popover-foot">
                ${isRight ? `
                    <button type="button" class="heb-action bw-action-speak" aria-label="Hear pronunciation" title="Hear pronunciation">
                        <span class="heb-action-icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                            </svg>
                        </span>
                        <span class="heb-action-label">Pronounce</span>
                    </button>
                ` : ''}
                <button type="button" class="heb-action bw-action-count" aria-label="Count occurrences across this translation" title="Count occurrences across this translation">
                    <span class="heb-action-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="4"  y1="9"  x2="20" y2="9"></line>
                            <line x1="4"  y1="15" x2="20" y2="15"></line>
                            <line x1="10" y1="3"  x2="8"  y2="21"></line>
                            <line x1="16" y1="3"  x2="14" y2="21"></line>
                        </svg>
                    </span>
                    <span class="heb-action-label">Count occurrences</span>
                </button>
            </div>
        `;
        document.body.appendChild(pop);
        this._wordPopover = pop;
        pop.addEventListener('click', (e) => e.stopPropagation());
        pop.querySelector('.bw-popover-close').addEventListener('click', () => this.closeWordPopover());
        pop.querySelector('.bw-action-speak')
            ?.addEventListener('click', () => this._speakWord(word, lang, pop));
        pop.querySelector('.bw-action-count')
            ?.addEventListener('click', () => this._countWordOccurrences(word, translation, pop));

        document.querySelectorAll('.bw-word.active').forEach(n => n.classList.remove('active'));
        wordEl.classList.add('active');
        this._positionPopoverNear(wordEl, pop);
    }

    _positionPopoverNear(anchor, pop) {
        // Generic copy of _positionHebrewPopover for the bw popover.
        const margin = 8;
        const aRect = anchor.getBoundingClientRect();
        const pRect = pop.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        let top = aRect.bottom + window.scrollY + margin;
        if (aRect.bottom + pRect.height + margin > vh) {
            top = aRect.top + window.scrollY - pRect.height - margin;
        }
        let left = aRect.left + window.scrollX + (aRect.width / 2) - (pRect.width / 2);
        const minLeft = window.scrollX + margin;
        const maxLeft = window.scrollX + vw - pRect.width - margin;
        if (left < minLeft) left = minLeft;
        if (left > maxLeft) left = maxLeft;
        if (top < window.scrollY + margin) top = window.scrollY + margin;
        pop.style.top = top + 'px';
        pop.style.left = left + 'px';
    }

    // Same playback strategy as _speakHebrewWord; lang is whatever
    // BCP-47 code matches the TTS engine.
    async _speakWord(word, lang, pop) {
        if (!word) return;
        const btn = pop?.querySelector('.bw-action-speak');
        if (btn) btn.classList.add('is-loading');
        if (this._bwAudio) {
            this._bwAudio._superseded = true;
            try { this._bwAudio.pause(); } catch {}
            try { this._bwAudio.removeAttribute('src'); this._bwAudio.load(); } catch {}
        }
        const audio = new Audio(`/api/tts?text=${encodeURIComponent(word)}&lang=${encodeURIComponent(lang || 'en')}`);
        this._bwAudio = audio;
        let played = false;
        audio.addEventListener('ended', () => {
            if (audio._superseded) return;
            if (btn) btn.classList.remove('is-playing');
        });
        audio.addEventListener('error', () => {
            if (audio._superseded || played) return;
            if (btn) btn.classList.remove('is-loading', 'is-playing');
            this.showToast?.('Pronunciation failed', 'error');
        });
        try {
            await audio.play();
            played = true;
            if (btn) {
                btn.classList.remove('is-loading');
                btn.classList.add('is-playing');
            }
        } catch (e) {
            if (audio._superseded) return;
            if (btn) btn.classList.remove('is-loading', 'is-playing');
            this.showToast?.('Pronunciation failed', 'error');
        }
    }

    async _countWordOccurrences(word, translation, pop) {
        const target = pop?.querySelector('.bw-popover-occurrences');
        const btn = pop?.querySelector('.bw-action-count');
        if (!target || !word) return;
        target.innerHTML = `<div class="heb-occ-loading">Counting…</div>`;
        if (btn) btn.disabled = true;
        try {
            const r = await fetch(
                `/api/words/occurrences?word=${encodeURIComponent(word)}` +
                `&translation=${encodeURIComponent(translation)}&limit=15`
            );
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (this._wordPopover !== pop) return;
            if (!data.count) {
                target.innerHTML = `
                    <div class="heb-occ-summary">
                        No occurrences found in ${this._escapeHtml(translation)}
                        (${data.corpus_size || 0} verses).
                    </div>`;
            } else {
                const samples = (data.samples || []).map(s => `
                    <li>
                        <button type="button" class="heb-occ-ref"
                            data-book="${this._escapeHtml(s.book)}"
                            data-chapter="${s.chapter}" data-verse="${s.verse}">
                            <span class="heb-occ-ref-label">${this._escapeHtml(s.book)} ${s.chapter}:${s.verse}</span>
                            ${s.hits > 1 ? `<span class="heb-occ-ref-hits">×${s.hits}</span>` : ''}
                        </button>
                    </li>
                `).join('');
                const more = data.verses_with_matches > (data.samples || []).length
                    ? `<div class="heb-occ-more">…and ${data.verses_with_matches - (data.samples || []).length} more verse(s).</div>`
                    : '';
                target.innerHTML = `
                    <div class="heb-occ-summary">
                        <strong>${data.count}</strong> occurrence${data.count === 1 ? '' : 's'}
                        in <strong>${data.verses_with_matches}</strong> verse${data.verses_with_matches === 1 ? '' : 's'}
                        across ${this._escapeHtml(translation)}.
                    </div>
                    <ul class="heb-occ-list">${samples}</ul>
                    ${more}
                `;
                target.querySelectorAll('.heb-occ-ref').forEach(ref => {
                    ref.addEventListener('click', () => {
                        const book = ref.dataset.book;
                        const chapter = parseInt(ref.dataset.chapter, 10);
                        if (typeof this.navigateToReference === 'function') {
                            this.navigateToReference(book, chapter);
                        } else {
                            this.currentBook = book;
                            this.currentChapter = chapter;
                            this.loadVerses?.();
                        }
                        this.closeWordPopover();
                    });
                });
            }
            if (this._wordPopover === pop) {
                const anchor = document.querySelector('.bw-word.active');
                if (anchor) this._positionPopoverNear(anchor, pop);
            }
        } catch (e) {
            target.innerHTML = `<div class="heb-occ-error">Failed to count occurrences.</div>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    _positionHebrewPopover(anchor, pop) {
        const margin = 8;
        const aRect = anchor.getBoundingClientRect();
        const pRect = pop.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        // Prefer placing the popover below the word; if it would overflow
        // vertically, place it above. Always clamp to the viewport.
        let top = aRect.bottom + window.scrollY + margin;
        if (aRect.bottom + pRect.height + margin > vh) {
            top = aRect.top + window.scrollY - pRect.height - margin;
        }
        let left = aRect.left + window.scrollX + (aRect.width / 2) - (pRect.width / 2);
        const minLeft = window.scrollX + margin;
        const maxLeft = window.scrollX + vw - pRect.width - margin;
        if (left < minLeft) left = minLeft;
        if (left > maxLeft) left = maxLeft;
        if (top < window.scrollY + margin) top = window.scrollY + margin;
        pop.style.top  = top + 'px';
        pop.style.left = left + 'px';
    }

    // ===== Pastor study tools =====
    // Per-verse action menu opens when the verse-number badge is tapped on
    // any verse in any view (3D book, parallel, or sync). Provides quick
    // access to: Compare translations, Copy with citation, Add/edit note,
    // Toggle bookmark, Highlight cycle.
    bindVerseActions() {
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (!(target instanceof HTMLElement)) return;
            // Close menu when clicking outside it.
            if (this._verseMenu && !this._verseMenu.contains(target)
                && !target.classList.contains('verse-num')) {
                this.closeVerseActionMenu();
            }
            if (target.classList.contains('verse-num')) {
                e.stopPropagation();
                this.openVerseActionMenu(target);
            }
        }, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._verseMenu) this.closeVerseActionMenu();
        });
        window.addEventListener('scroll', () => this.closeVerseActionMenu(), true);
        window.addEventListener('resize', () => this.closeVerseActionMenu());
    }

    closeVerseActionMenu() {
        if (this._verseMenu) { this._verseMenu.remove(); this._verseMenu = null; }
    }

    // Determine which (book, chapter, translation) a verse element belongs
    // to by walking up to a known container. Falls back to the reader's
    // current state for the 3D book view.
    _verseContext(verseEl) {
        const book = this.currentBook;
        const chapter = this.currentChapter;
        const verse = parseInt(verseEl.closest('[data-verse]')?.dataset.verse, 10);
        let translation = this.currentTranslation;
        // Walk up looking for the container that tells us which translation.
        let n = verseEl;
        while (n && n !== document.body) {
            const id = n.id;
            if (id === 'col1Verses')      { translation = this.parallelTrans1; break; }
            if (id === 'col2Verses')      { translation = this.parallelTrans2; break; }
            if (id === 'syncVerses1')     { translation = this.syncTrans1; break; }
            if (id === 'syncVerses2')     { translation = this.syncTrans2; break; }
            if (id === 'leftVerses' || id === 'rightVerses') { translation = this.currentTranslation; break; }
            n = n.parentElement;
        }
        return { book, chapter, verse, translation };
    }

    openVerseActionMenu(verseNumEl) {
        this.closeVerseActionMenu();
        this.closeHebrewPopover();
        const verseEl = verseNumEl.closest('[data-verse]');
        if (!verseEl) return;
        const ctx = this._verseContext(verseNumEl);
        if (!ctx.verse) return;

        const ud = window.userdata;
        const isBookmarked = ud?.isBookmarked?.(ctx.book, ctx.chapter, ctx.verse);
        const note = ud?.getNote?.(ctx.verse);
        const hl = ud?.getHighlight?.(ctx.verse);

        const menu = document.createElement('div');
        menu.className = 'verse-menu';
        menu.setAttribute('role', 'menu');
        menu.innerHTML = `
            <div class="verse-menu-header">
                <strong>${ctx.book} ${ctx.chapter}:${ctx.verse}</strong>
                <span class="verse-menu-trans">${this._escapeHtml(ctx.translation || '')}</span>
            </div>
            <button type="button" class="verse-menu-item" data-act="compare">
                <span class="vm-icon">⇄</span> Compare translations
            </button>
            <button type="button" class="verse-menu-item" data-act="copy">
                <span class="vm-icon">⧉</span> Copy with citation
            </button>
            <button type="button" class="verse-menu-item" data-act="note">
                <span class="vm-icon">✎</span> ${note ? 'Edit note' : 'Add note'}
            </button>
            <button type="button" class="verse-menu-item" data-act="bookmark">
                <span class="vm-icon">${isBookmarked ? '★' : '☆'}</span>
                ${isBookmarked ? 'Remove bookmark' : 'Add bookmark'}
            </button>
            <button type="button" class="verse-menu-item" data-act="highlight">
                <span class="vm-icon" style="background:${hl?.color || 'transparent'};border-radius:3px;display:inline-block;width:14px;height:14px;border:1px solid var(--border-color);"></span>
                ${hl ? 'Change highlight' : 'Highlight'}
            </button>
        `;
        document.body.appendChild(menu);
        this._verseMenu = menu;
        menu.addEventListener('click', (e) => e.stopPropagation());
        this._positionFloatingNear(verseNumEl, menu);

        menu.querySelectorAll('.verse-menu-item').forEach(btn => {
            btn.addEventListener('click', async () => {
                const act = btn.dataset.act;
                this.closeVerseActionMenu();
                if (act === 'compare')   return this.openCompareTranslations(ctx);
                if (act === 'copy')      return this.copyVerseWithCitation(ctx);
                if (act === 'note')      return this.promptVerseNote(ctx);
                if (act === 'bookmark')  return this.toggleVerseBookmark(ctx);
                if (act === 'highlight') return this.cycleVerseHighlight(ctx);
            });
        });
    }

    _positionFloatingNear(anchor, el) {
        // Generic copy of _positionHebrewPopover, kept separate so the two
        // floating widgets can have different sizes / margins later.
        const margin = 8;
        const aRect = anchor.getBoundingClientRect();
        const eRect = el.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        let top = aRect.bottom + window.scrollY + margin;
        if (aRect.bottom + eRect.height + margin > vh) {
            top = aRect.top + window.scrollY - eRect.height - margin;
        }
        let left = aRect.left + window.scrollX;
        const maxLeft = window.scrollX + vw - eRect.width - margin;
        if (left > maxLeft) left = maxLeft;
        if (left < window.scrollX + margin) left = window.scrollX + margin;
        if (top < window.scrollY + margin) top = window.scrollY + margin;
        el.style.top = top + 'px';
        el.style.left = left + 'px';
    }

    // ----- Compare translations modal -----
    async openCompareTranslations(ctx) {
        const overlay = document.getElementById('compareOverlay');
        if (!overlay) return;
        const list = document.getElementById('compareList');
        const cite = document.getElementById('compareCitation');
        const title = document.getElementById('compareTitle');
        title.textContent = `Compare — ${ctx.book} ${ctx.chapter}:${ctx.verse}`;
        cite.textContent = `Showing ${ctx.book} ${ctx.chapter}:${ctx.verse} across all available translations.`;
        list.innerHTML = `<div class="compare-loading">Loading translations…</div>`;
        overlay.classList.add('active');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');

        // Make sure the catalog is loaded.
        let trans = (this.allTranslations || []).map(t => (typeof t === 'string' ? t : t.value));
        if (!trans.length) {
            try {
                const r = await fetch('/api/translations');
                if (r.ok) {
                    const data = await r.json();
                    trans = Array.isArray(data) ? data : (data.translations || []);
                }
            } catch {}
        }

        // Fetch all translations for this chapter in parallel.
        const results = await Promise.all(trans.map(async (t) => {
            try {
                const r = await fetch(`/api/verses/${ctx.book}/${ctx.chapter}?translation=${encodeURIComponent(t)}`);
                if (!r.ok) return { t, err: true };
                const data = await r.json();
                const verses = data.verses || data;
                const text = verses[ctx.verse] || verses[String(ctx.verse)] || '';
                return { t, actual: data.translation || t, fallback: !!data.fallback, text };
            } catch {
                return { t, err: true };
            }
        }));

        const HEB = /[\u0590-\u05FF]/;
        list.innerHTML = results.map(r => {
            if (r.err) {
                return `
                    <div class="compare-row compare-row-empty">
                        <div class="compare-trans">${this._escapeHtml(r.t)}</div>
                        <div class="compare-text compare-text-empty">Failed to load.</div>
                    </div>`;
            }
            if (!r.text) {
                return `
                    <div class="compare-row compare-row-empty">
                        <div class="compare-trans">${this._escapeHtml(r.t)}</div>
                        <div class="compare-text compare-text-empty">Not available for this verse.</div>
                    </div>`;
            }
            const isHeb = HEB.test(r.text);
            const label = r.fallback
                ? `${this._escapeHtml(r.t)} <span class="compare-fallback">→ ${this._escapeHtml(r.actual)}</span>`
                : this._escapeHtml(r.t);
            return `
                <div class="compare-row">
                    <div class="compare-trans">${label}</div>
                    <div class="compare-text"${isHeb ? ' dir="rtl" lang="he"' : ''}>${this._escapeHtml(r.text)}</div>
                    <button type="button" class="compare-copy" data-trans="${this._escapeHtml(r.actual || r.t)}" data-text="${this._escapeHtml(r.text)}" title="Copy this translation with citation">⧉</button>
                </div>`;
        }).join('');

        list.querySelectorAll('.compare-copy').forEach(btn => {
            btn.addEventListener('click', () => {
                this._copyToClipboard(this._formatCitation(
                    ctx.book, ctx.chapter, ctx.verse,
                    btn.dataset.text, btn.dataset.trans));
                this.showToast('Copied with citation', 'info');
            });
        });
    }

    closeCompareModal() {
        const overlay = document.getElementById('compareOverlay');
        if (!overlay) return;
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
    }

    // ----- Per-verse actions -----
    _formatCitation(book, chapter, verse, text, translation) {
        return `"${(text || '').trim()}" — ${book} ${chapter}:${verse} (${translation || ''})`.trim();
    }

    async _copyToClipboard(text) {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                return true;
            }
        } catch {}
        // Fallback for non-secure contexts (e.g. http://).
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
            return true;
        } catch {
            return false;
        }
    }

    async copyVerseWithCitation(ctx) {
        // Pull the verse text out of the rendered DOM if we can; otherwise fetch.
        let text = '';
        const containerEl = document.querySelector(
            `#${this._containerIdFor(ctx)} [data-verse="${ctx.verse}"]`
        );
        if (containerEl) {
            text = containerEl.textContent.replace(/^\s*\d+\s*/, '').trim();
        } else {
            try {
                const r = await fetch(`/api/verses/${ctx.book}/${ctx.chapter}?translation=${encodeURIComponent(ctx.translation)}`);
                if (r.ok) {
                    const data = await r.json();
                    text = (data.verses || data)[ctx.verse] || '';
                }
            } catch {}
        }
        const cit = this._formatCitation(ctx.book, ctx.chapter, ctx.verse, text, ctx.translation);
        const ok = await this._copyToClipboard(cit);
        this.showToast(ok ? 'Copied with citation' : 'Copy failed', ok ? 'info' : 'error');
    }

    _containerIdFor(ctx) {
        // Pick whichever DOM container currently holds the verse text for
        // the supplied translation. Used for in-place text extraction.
        if (this.parallelTrans1 === ctx.translation) return 'col1Verses';
        if (this.parallelTrans2 === ctx.translation) return 'col2Verses';
        if (this.syncTrans1 === ctx.translation)     return 'syncVerses1';
        if (this.syncTrans2 === ctx.translation)     return 'syncVerses2';
        return 'leftVerses'; // best-effort
    }

    async promptVerseNote(ctx) {
        const ud = window.userdata;
        if (!ud?.setNote) return this.showToast('Notes unavailable', 'error');
        const existing = (ud.getNote?.(ctx.verse) || {}).body || '';
        const updated = window.prompt(
            `Note for ${ctx.book} ${ctx.chapter}:${ctx.verse}`,
            existing
        );
        if (updated === null) return;
        const ok = await ud.setNote(ctx.book, ctx.chapter, ctx.verse, updated.trim());
        this.showToast(ok ? 'Note saved' : 'Note failed to save', ok ? 'info' : 'error');
        if (ok && typeof this._applyVerseAnnotations === 'function') {
            this._applyVerseAnnotations();
        }
    }

    async toggleVerseBookmark(ctx) {
        const ud = window.userdata;
        if (!ud) return this.showToast('Bookmarks unavailable', 'error');
        if (ud.isBookmarked?.(ctx.book, ctx.chapter, ctx.verse)) {
            const found = ud.bookmarks?.find(b =>
                b.book === ctx.book && b.chapter === ctx.chapter && +b.verse === +ctx.verse);
            if (found) await ud.removeBookmark(found.id);
            this.showToast('Bookmark removed', 'info');
        } else {
            await ud.addBookmark(ctx.book, ctx.chapter, ctx.verse, '');
            this.showToast('Bookmark added', 'info');
        }
        if (typeof this._applyVerseAnnotations === 'function') this._applyVerseAnnotations();
    }

    async cycleVerseHighlight(ctx) {
        const ud = window.userdata;
        if (!ud?.setHighlight) return this.showToast('Highlights unavailable', 'error');
        const order = ['yellow', 'green', 'blue', 'pink', ''];
        const current = ud.getHighlight?.(ctx.verse)?.color || '';
        const next = order[(order.indexOf(current) + 1) % order.length];
        const ok = await ud.setHighlight(ctx.book, ctx.chapter, ctx.verse, next);
        this.showToast(ok ? (next ? `Highlighted ${next}` : 'Highlight cleared') : 'Highlight failed',
            ok ? 'info' : 'error');
        if (ok && typeof this._applyVerseAnnotations === 'function') {
            this._applyVerseAnnotations();
        }
    }

    // ----- Study Tools dialog -----
    bindStudyTools() {
        const btn = document.getElementById('studyToolsBtn');
        const overlay = document.getElementById('studyToolsOverlay');
        if (!btn || !overlay) return;
        const closeBtn = document.getElementById('studyToolsClose');
        const compareCloseBtn = document.getElementById('compareClose');
        const compareOverlay  = document.getElementById('compareOverlay');

        const open = () => {
            const lbl = document.getElementById('studyCurrentLabel');
            if (lbl) lbl.textContent = `${this.currentBook} ${this.currentChapter} (${this.currentTranslation})`;
            overlay.classList.add('active');
            overlay.setAttribute('aria-hidden', 'false');
            document.body.classList.add('modal-open');
        };
        const close = () => {
            overlay.classList.remove('active');
            overlay.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('modal-open');
        };
        btn.addEventListener('click', open);
        closeBtn?.addEventListener('click', close);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

        compareCloseBtn?.addEventListener('click', () => this.closeCompareModal());
        compareOverlay?.addEventListener('click', (e) => {
            if (e.target === compareOverlay) this.closeCompareModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (overlay.classList.contains('active')) close();
            if (compareOverlay?.classList.contains('active')) this.closeCompareModal();
        });

        document.getElementById('studyExportChapterMd')?.addEventListener('click', () => {
            const url = `/api/me/export/chapter/${encodeURIComponent(this.currentBook)}/${this.currentChapter}?translation=${encodeURIComponent(this.currentTranslation)}`;
            window.location.href = url;
        });
        document.getElementById('studyCopyChapterText')?.addEventListener('click', async () => {
            const r = await fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${encodeURIComponent(this.currentTranslation)}`);
            if (!r.ok) return this.showToast('Failed to load chapter', 'error');
            const data = await r.json();
            const verses = data.verses || data;
            const lines = [`${this.currentBook} ${this.currentChapter} (${data.translation || this.currentTranslation})`, ''];
            for (const k of Object.keys(verses).map(Number).sort((a, b) => a - b)) {
                lines.push(`${k}. ${verses[k]}`);
            }
            const ok = await this._copyToClipboard(lines.join('\n'));
            this.showToast(ok ? 'Chapter copied to clipboard' : 'Copy failed', ok ? 'info' : 'error');
        });
        document.getElementById('studyExportAllNotes')?.addEventListener('click', () => {
            window.location.href = '/api/me/export/notes';
        });
        document.getElementById('studyExportAllBookmarks')?.addEventListener('click', () => {
            window.location.href = '/api/me/export/bookmarks';
        });
    }

    async _fetchOnlineVoices() {
        if (this._onlineVoicesCache) return this._onlineVoicesCache;
        try {
            const r = await fetch('/api/tts/voices');
            if (!r.ok) return null;
            this._onlineVoicesCache = await r.json();
            return this._onlineVoicesCache;
        } catch (e) {
            console.warn('Failed to fetch online voices', e);
            return null;
        }
    }

    async populateVoiceSettings() {
        // Online voices come from the server (curated list of Microsoft
        // Edge neural voices). Browser voices come from speechSynthesis.
        const [onlineCatalog, voices] = await Promise.all([
            this._fetchOnlineVoices(),
            this.waitForVoices(800),
        ]);

        const fillBrowser = (id, baseLang) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const matches = voices
                .filter(v => (v.lang || '').toLowerCase().startsWith(baseLang))
                .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
            sel.innerHTML = '';
            const auto = document.createElement('option');
            auto.value = '';
            auto.textContent = matches.length
                ? '— Default (auto-select) —'
                : '— No browser voices installed —';
            sel.appendChild(auto);
            matches.forEach(v => {
                const o = document.createElement('option');
                o.value = v.voiceURI || v.name;
                o.textContent = `${v.name} (${v.lang})${v.default ? ' • default' : ''}`;
                sel.appendChild(o);
            });
            const want = (this.ttsSettings.voice && this.ttsSettings.voice[baseLang]) || '';
            sel.value = want;
            if (sel.value !== want) sel.value = '';
        };

        const fillOnline = (id, baseLang) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const list = (onlineCatalog && onlineCatalog[baseLang]) || [];
            sel.innerHTML = '';
            const auto = document.createElement('option');
            auto.value = '';
            auto.textContent = list.length
                ? '— Default —'
                : '— Online voices unavailable —';
            sel.appendChild(auto);
            list.forEach(v => {
                const o = document.createElement('option');
                o.value = v.id;
                o.textContent = v.label;
                sel.appendChild(o);
            });
            const want = (this.ttsSettings.onlineVoice && this.ttsSettings.onlineVoice[baseLang]) || '';
            sel.value = want;
            if (sel.value !== want) sel.value = '';
        };

        fillBrowser('ttsVoiceEn', 'en');
        fillBrowser('ttsVoiceHu', 'hu');
        fillBrowser('ttsVoiceHe', 'he');
        fillOnline('ttsOnlineVoiceEn', 'en');
        fillOnline('ttsOnlineVoiceHu', 'hu');
        fillOnline('ttsOnlineVoiceHe', 'he');

        const preferEl = document.getElementById('ttsPreferServer');
        if (preferEl) preferEl.checked = !!this.ttsSettings.preferServer;
    }

    testTTSVoice() {
        const transName = (document.getElementById('syncTrans1')?.value)
            || this.currentTranslation || 'NIV';
        const lang = this.ttsLangFor(transName);
        const samples = {
            'en-US': 'For God so loved the world that he gave his one and only Son.',
            'hu-HU': 'Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta.',
            'he-IL': 'כִּי כָּכָה אָהַב הָאֱלֹהִים אֶת־הָעוֹלָם.',
        };
        const text = samples[lang] || samples['en-US'];
        try { window.speechSynthesis.cancel(); } catch {}
        if (this._testAudio) { try { this._testAudio.pause(); } catch {} this._testAudio = null; }

        if (this.ttsShouldForceServer(lang)) {
            const base = lang.split('-')[0];
            const tld = this.ttsSettings.tld || 'com';
            const onlineVoice = (this.ttsSettings.onlineVoice && this.ttsSettings.onlineVoice[base]) || '';
            let url = `/api/tts?lang=${encodeURIComponent(base)}`
                + `&tld=${encodeURIComponent(tld)}`
                + `&text=${encodeURIComponent(text)}`;
            if (onlineVoice) url += `&voice=${encodeURIComponent(onlineVoice)}`;
            const a = new Audio(url);
            a.playbackRate = this.playbackRate || 1;
            this._testAudio = a;
            a.play().catch(err => {
                console.warn('Voice test failed', err);
                this.showToast('Could not play test audio', 'error');
            });
            return;
        }
        const u = new SpeechSynthesisUtterance(text);
        u.lang = lang;
        u.rate = this.playbackRate || 1;
        const voice = this.pickTTSVoice(lang);
        if (voice) u.voice = voice;
        window.speechSynthesis.speak(u);
    }

    // Split long text into ~160-char chunks at sentence/clause boundaries.
    // Works around Chrome's ~200-char / ~15-second utterance bug and
    // improves reliability on iOS Safari.
    chunkTextForTTS(text, maxLen = 160) {
        const clean = (text || '').trim();
        if (!clean) return [];
        if (clean.length <= maxLen) return [clean];
        const parts = clean.split(/(?<=[.!?,:;—–])\s+/);
        const out = [];
        let buf = '';
        for (const p of parts) {
            if ((buf + ' ' + p).trim().length <= maxLen) {
                buf = (buf ? buf + ' ' : '') + p;
            } else {
                if (buf) out.push(buf);
                if (p.length <= maxLen) {
                    buf = p;
                } else {
                    // Hard split very long token-runs by spaces
                    const words = p.split(' ');
                    let line = '';
                    for (const w of words) {
                        if ((line + ' ' + w).trim().length <= maxLen) {
                            line = (line ? line + ' ' : '') + w;
                        } else {
                            if (line) out.push(line);
                            line = w;
                        }
                    }
                    buf = line;
                }
            }
        }
        if (buf) out.push(buf);
        return out;
    }

    toggleTTS() {
        const hasSpeech = ('speechSynthesis' in window) && ('SpeechSynthesisUtterance' in window);
        if (!hasSpeech) {
            // No native TTS at all → go straight to server fallback
            this.startTTS({ forceServer: true });
            return;
        }
        if (this.ttsState === 'playing') {
            this.pauseTTS();
            return;
        }
        if (this.ttsState === 'paused') {
            this.resumeTTS();
            return;
        }
        this.startTTS();
    }

    pauseTTS() {
        if (this.ttsMode === 'audio' && this.ttsAudio) {
            this.ttsAudio.pause();
        } else if (window.speechSynthesis) {
            window.speechSynthesis.pause();
        }
        this.ttsState = 'paused';
        this.setPlayBtnPlaying(false);
        this.stopTTSKeepalive();
    }

    resumeTTS() {
        if (this.ttsMode === 'audio' && this.ttsAudio) {
            this.ttsAudio.play().catch(() => {});
        } else if (window.speechSynthesis) {
            window.speechSynthesis.resume();
            this.startTTSKeepalive();
        }
        this.ttsState = 'playing';
        this.setPlayBtnPlaying(true);
    }

    // Re-queue TTS from the current verse using whatever the visible
    // sync column now is. Called after a translation swap/change so the
    // new language is read aloud instead of finishing the old queue.
    restartTTSIfPlaying() {
        if (this.ttsState !== 'playing') return;
        const currentVerse = this.ttsQueue[this.ttsIndex] && this.ttsQueue[this.ttsIndex].verse;
        // Invalidate any in-flight audio/utterance callbacks so they
        // can't bump ttsIndex on the freshly-rebuilt queue.
        this._ttsGen = (this._ttsGen || 0) + 1;
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        if (this.ttsAudio) {
            try {
                this.ttsAudio.onended = null;
                this.ttsAudio.onerror = null;
                this.ttsAudio.pause();
                this.ttsAudio.src = '';
            } catch {}
            this.ttsAudio = null;
        }
        this.currentUtterance = null;
        const verses = this.collectVisibleVerses();
        if (!verses.length) { this.stopTTS(); return; }
        let resumeIdx = 0;
        if (currentVerse) {
            const i = verses.findIndex(v => String(v.verse) === String(currentVerse));
            if (i >= 0) resumeIdx = i;
        }
        this.ttsQueue = verses;
        this.ttsIndex = resumeIdx;
        const lang = verses[resumeIdx].lang;
        const useServer = this.ttsShouldForceServer(lang) || !window.speechSynthesis;
        this.ttsMode = useServer ? 'audio' : 'speech';
        this.speakNextTTS();
    }

    async startTTS(opts = {}) {
        // The right column is the intended "Read aloud" source. If the
        // sync render hasn't populated it yet (e.g. user pressed play
        // very quickly after navigating), wait for it before queueing
        // so we don't accidentally lock TTS onto the English left column.
        const col2 = document.getElementById('syncVerses2');
        const col2El = col2 && col2.closest('.sync-column');
        const col2Hidden = (col2El && col2El.classList.contains('hidden-column')) || !!this.hebrewDisabled;
        if (col2 && !col2Hidden && col2.querySelectorAll('.sync-verse').length === 0) {
            try { await this.renderSyncText(); } catch {}
        }
        const verses = this.collectVisibleVerses();
        if (!verses.length) {
            this.showToast('No text available to read', 'info');
            return;
        }
        // For Hebrew, prefer the RITDorg YouTube video if one exists for
        // this chapter. Falls through to gTTS, which itself falls through
        // to the local browser voice if it 503s.
        const firstLang = (verses[0] && verses[0].lang || '').toLowerCase().split('-')[0];
        if (!opts._videoChecked && firstLang === 'he') {
            try {
                const r = await fetch(`/api/sync/${this.currentBook}/${this.currentChapter}`);
                if (r.ok) {
                    const d = await r.json();
                    if (d && (d.video_id || d.playlist_id)) {
                        this.showToast('Playing RITDorg video for this chapter', 'info');
                        try { await this.loadVideoSync(); } catch {}
                        if (this.player && this.isPlayerReady) {
                            try { this.player.playVideo(); } catch {}
                            return;
                        }
                    }
                }
            } catch {}
        }
        // Cancel any previous queue
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        if (this.ttsAudio) { try { this.ttsAudio.pause(); } catch {} this.ttsAudio = null; }
        this.ttsQueue = verses;
        this.ttsIndex = 0;
        this.ttsState = 'playing';
        this.ttsMode = null; // 'speech' | 'audio'
        this.setPlayBtnPlaying(true);
        const np = document.getElementById('nowPlayingText');
        if (np) np.textContent = `${this.currentBook} ${this.currentChapter} (Read aloud)`;
        const status = document.getElementById('syncStatusText');
        if (status) status.textContent = 'Reading…';

        const lang = verses[0].lang;
        // Prefer server-side Google TTS by default — it's far more
        // consistent across browsers/devices and supports every language
        // we ship. Callers may pass `preferBrowser:true` to opt into the
        // local SpeechSynthesis path; otherwise we only use it as a
        // fallback when the server can't deliver audio.
        let useServer = !opts.preferBrowser;
        if (opts.forceServer) useServer = true;
        if (this.ttsShouldForceServer(lang)) useServer = true;
        if (useServer && !('Audio' in window)) {
            // Extremely unlikely, but if there's no <audio> support fall
            // back to whatever native synthesis is available.
            useServer = false;
        }
        if (!useServer && window.speechSynthesis) {
            await this.waitForVoices(1500);
            const voice = this.pickTTSVoice(lang);
            if (!voice) {
                // No installed voice for this language → use server mp3
                useServer = true;
            }
        }
        this.ttsMode = useServer ? 'audio' : 'speech';
        this.speakNextTTS();
    }

    collectVisibleVerses() {
        // The RIGHT column is the "Read aloud" source; the LEFT column is
        // the "Follow along" mirror. Prefer the right column unless it's
        // hidden (e.g. user toggled the Hebrew column off, or it fell back
        // to a translation that doesn't carry this passage).
        const containers = ['syncVerses2', 'syncVerses1'];
        for (const id of containers) {
            const c = document.getElementById(id);
            if (!c) continue;
            const colEl = c.closest('.sync-column');
            if (colEl && colEl.classList.contains('hidden-column')) continue;
            // The Hebrew column is also hidden when the user disables it.
            if (id === 'syncVerses2' && this.hebrewDisabled) continue;
            const nodes = Array.from(c.querySelectorAll('.sync-verse'));
            if (!nodes.length) continue;
            const transName = (id === 'syncVerses1') ? this.syncTrans1 : this.syncTrans2;
            const lang = this.ttsLangFor(transName);
            return nodes.map(n => ({
                el: n,
                verse: n.dataset.verse,
                text: (n.innerText || n.textContent || '').replace(/^\s*\d+\s*/, '').trim(),
                lang,
            })).filter(v => v.text);
        }
        return [];
    }

    // Smoothly center a verse element within its scrollable .sync-verses
    // container without affecting page scroll. Uses the sync-scroll
    // suppress hook so it doesn't bounce the cross-column mirror.
    centerVerseInColumn(verseEl) {
        if (!verseEl) return;
        const container = verseEl.closest('.sync-verses');
        if (!container) return;
        const cRect = container.getBoundingClientRect();
        const vRect = verseEl.getBoundingClientRect();
        const verseCenter = (vRect.top - cRect.top) + container.scrollTop + (vRect.height / 2);
        let target = verseCenter - (cRect.height / 2);
        target = Math.max(0, Math.min(target, container.scrollHeight - container.clientHeight));
        if (Math.abs(target - container.scrollTop) < 2) return;
        const doScroll = () => {
            try {
                container.scrollTo({ top: target, behavior: 'smooth' });
            } catch {
                container.scrollTop = target;
            }
        };
        if (this._suppressSyncScroll) {
            this._suppressSyncScroll(doScroll, 700);
        } else {
            doScroll();
        }
    }

    speakNextTTS() {
        if (this.ttsState !== 'playing') return;
        if (this.ttsIndex >= this.ttsQueue.length) {
            // End of chapter — auto-advance if enabled and a next chapter exists.
            if (this.autoAdvanceChapter) {
                const sel = document.getElementById('chapterSelect');
                const maxChapter = sel ? sel.options.length : 0;
                if (this.currentChapter < maxChapter) {
                    this._autoplayAfterLoad = true;
                    this.nextChapter();
                    return;
                }
            }
            this.stopTTS();
            return;
        }
        const item = this.ttsQueue[this.ttsIndex];
        document.querySelectorAll('.sync-verse.active, .sync-verse.follow-active')
            .forEach(v => v.classList.remove('active', 'follow-active'));
        if (item.el) {
            item.el.classList.add('active');
            this.centerVerseInColumn(item.el);
            // Mirror the active verse on the opposite ("follow along") column.
            const verseNum = item.el.dataset.verse;
            if (verseNum) {
                document.querySelectorAll(`.sync-verse[data-verse="${verseNum}"]`)
                    .forEach(other => {
                        if (other !== item.el) {
                            other.classList.add('follow-active');
                            // Keep both columns visually aligned on the
                            // current verse, regardless of which one is
                            // the audio source.
                            this.centerVerseInColumn(other);
                        }
                    });
            }
        }
        this.updateTTSProgress();

        if (this.ttsMode === 'audio') {
            this.speakViaServer(item);
        } else {
            this.speakViaSynthesis(item);
        }
    }

    speakViaSynthesis(item) {
        const chunks = this.chunkTextForTTS(item.text);
        if (!chunks.length) {
            this.ttsIndex += 1;
            this.speakNextTTS();
            return;
        }
        const myGen = (this._ttsGen = this._ttsGen || 0);
        const voice = this.pickTTSVoice(item.lang);
        let i = 0;
        const failVerseToServer = () => {
            if (myGen !== this._ttsGen) return;
            try { window.speechSynthesis.cancel(); } catch {}
            this.ttsMode = 'audio';
            this.speakViaServer(item);
        };
        const speakChunk = () => {
            if (this.ttsState !== 'playing') return;
            if (myGen !== this._ttsGen) return; // queue rebuilt, abandon
            if (i >= chunks.length) {
                this.ttsIndex += 1;
                this.speakNextTTS();
                return;
            }
            const u = new SpeechSynthesisUtterance(chunks[i]);
            u.lang = item.lang;
            u.rate = this.playbackRate || 1;
            if (voice) u.voice = voice;
            const startedAt = performance.now();
            const minMs = Math.max(120, chunks[i].length * 18);
            u.onend = () => {
                if (myGen !== this._ttsGen) return;
                const elapsed = performance.now() - startedAt;
                if (elapsed < Math.min(minMs, 400)) {
                    console.warn('TTS finished suspiciously fast', { elapsed, chunk: chunks[i] });
                    failVerseToServer();
                    return;
                }
                i += 1;
                speakChunk();
            };
            u.onerror = (e) => {
                if (myGen !== this._ttsGen) return;
                console.warn('SpeechSynthesis error', e);
                failVerseToServer();
            };
            this.currentUtterance = u;
            window.speechSynthesis.speak(u);
            this.startTTSKeepalive();
        };
        speakChunk();
    }

    speakViaServer(item) {
        try {
            if (this.ttsAudio) {
                try {
                    this.ttsAudio.onended = null;
                    this.ttsAudio.onerror = null;
                    this.ttsAudio.pause();
                } catch {}
            }
            const myGen = (this._ttsGen = this._ttsGen || 0);
            const lang = (item.lang || 'en').split('-')[0];
            const tld = (this.ttsSettings && this.ttsSettings.tld) || 'com';
            // User-chosen Microsoft Edge neural voice for this language,
            // if any. Server falls back to a sane per-language default.
            const onlineVoice = (this.ttsSettings && this.ttsSettings.onlineVoice
                                 && this.ttsSettings.onlineVoice[lang]) || '';
            let url = `/api/tts?lang=${encodeURIComponent(lang)}`
                + `&tld=${encodeURIComponent(tld)}`
                + `&text=${encodeURIComponent(item.text)}`;
            if (onlineVoice) url += `&voice=${encodeURIComponent(onlineVoice)}`;
            const audio = new Audio(url);
            audio.playbackRate = this.playbackRate || 1;
            audio.preload = 'auto';
            audio.onended = () => {
                if (myGen !== this._ttsGen) return; // stale, queue was rebuilt
                this.ttsIndex += 1;
                this.speakNextTTS();
            };
            audio.onerror = () => {
                if (myGen !== this._ttsGen) return;
                console.warn('Server TTS failed for verse', item.verse, '- falling back to browser TTS');
                if (window.speechSynthesis && !this._serverTTSWarned) {
                    this._serverTTSWarned = true;
                    this.showToast('Online voice unavailable, using device voice', 'info');
                }
                if (window.speechSynthesis) {
                    this.speakViaSynthesis(item);
                } else {
                    this.ttsIndex += 1;
                    this.speakNextTTS();
                }
            };
            this.ttsAudio = audio;
            const p = audio.play();
            if (p && p.catch) p.catch(err => {
                if (myGen !== this._ttsGen) return;
                console.warn('Audio.play rejected', err);
                this.stopTTS();
                this.showToast('Tap play to start audio', 'info');
            });
        } catch (err) {
            console.warn('speakViaServer error', err);
            this.ttsIndex += 1;
            this.speakNextTTS();
        }
    }

    // Chrome on desktop stops speaking utterances after ~15s. Calling
    // pause()/resume() periodically keeps the engine alive.
    startTTSKeepalive() {
        this.stopTTSKeepalive();
        this.ttsKeepalive = setInterval(() => {
            if (!window.speechSynthesis) return;
            if (this.ttsState !== 'playing') return;
            if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
                window.speechSynthesis.pause();
                window.speechSynthesis.resume();
            }
        }, 10000);
    }
    stopTTSKeepalive() {
        if (this.ttsKeepalive) {
            clearInterval(this.ttsKeepalive);
            this.ttsKeepalive = null;
        }
    }

    stopTTS() {
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        if (this.ttsAudio) { try { this.ttsAudio.pause(); } catch {} this.ttsAudio = null; }
        this.stopTTSKeepalive();
        this.ttsState = 'idle';
        this.ttsIndex = 0;
        this.ttsQueue = [];
        this.currentUtterance = null;
        this.ttsMode = null;
        this.setPlayBtnPlaying(false);
        document.querySelectorAll('.sync-verse.active, .sync-verse.follow-active')
            .forEach(v => v.classList.remove('active', 'follow-active'));
        const fill = document.getElementById('progressFill');
        if (fill) fill.style.width = '0%';
        const time = document.getElementById('timeDisplay');
        if (time) time.textContent = '0 / 0';
        const status = document.getElementById('syncStatusText');
        if (status) status.textContent = '';
    }

    setPlayBtnPlaying(isPlaying) {
        const btn = document.getElementById('playPauseBtn');
        if (!btn) return;
        btn.classList.toggle('playing', !!isPlaying);
    }

    updateTTSProgress() {
        const total = this.ttsQueue.length || 1;
        const pct = Math.min(100, ((this.ttsIndex) / total) * 100);
        const fill = document.getElementById('progressFill');
        if (fill) fill.style.width = `${pct}%`;
        const time = document.getElementById('timeDisplay');
        if (time) time.textContent = `${Math.min(this.ttsIndex + 1, total)} / ${total}`;
    }

    // Set playback rate (UI + player). Chooses nearest supported rate for YouTube.
    setPlaybackRate(rate) {
        this.playbackRate = Number(rate) || 1;
        const label = document.getElementById('rateLabel');
        if (label) label.textContent = `${this.playbackRate}×`;

        if (!this.player || !this.isPlayerReady) return;

        try {
            // Prefer rounding to one of the available playback rates reported by the player
            if (typeof this.player.getAvailablePlaybackRates === 'function') {
                const avail = this.player.getAvailablePlaybackRates() || [];
                if (Array.isArray(avail) && avail.length > 0) {
                    let closest = avail.reduce((a, b) => Math.abs(a - this.playbackRate) < Math.abs(b - this.playbackRate) ? a : b);
                    this.player.setPlaybackRate(closest);
                    return;
                }
            }
            // Fallback: try setting directly
            if (typeof this.player.setPlaybackRate === 'function') {
                this.player.setPlaybackRate(this.playbackRate);
            }
        } catch (err) {
            console.warn('Playback rate unsupported or failed to set', err);
        }
    }
    
    seekVideo(e) {
        if (!this.player || !this.isPlayerReady) return;
        
        const rect = e.currentTarget.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        const duration = this.player.getDuration();
        this.player.seekTo(percent * duration, true);
    }
    
    startSyncInterval() {
        this.stopSyncInterval();
        
        this.syncInterval = setInterval(() => {
            if (!this.player || !this.isPlayerReady) return;
            
            const currentTime = this.player.getCurrentTime();
            const duration = this.player.getDuration();
            
            // Update progress bar
            const progress = (currentTime / duration) * 100;
            document.getElementById('progressFill').style.width = `${progress}%`;
            
            // Update time display
            this.updateTimeDisplay();
            
            // Sync verse and words very frequently for real-time feel
            this.syncWithCaptions(currentTime, duration);
        }, 50);
    }
    
    stopSyncInterval() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }
    
    async fetchCaptions(videoId) {
        // Skip fetching captions for placeholder video IDs
        if (videoId === 'placeholder_video_id' || !videoId) {
            console.log('Skipping caption fetch for placeholder video ID');
            this.captions = null;
            this.lastCaptionVideoId = null;
            this.showToast('No video available for this chapter - captions disabled', 'info');
            document.getElementById('syncStatusText').textContent = 'No video available';
            return;
        }

        if (this.lastCaptionVideoId === videoId && Array.isArray(this.captions) && this.captions.length > 0) {
            return;
        }

        const fetchToken = ++this.captionFetchToken;
        this.lastCaptionVideoId = videoId;
        
        try {
            const tracks = this.getCaptionTracksFromPlayer();
            const selectedTrack = this.pickCaptionTrack(tracks);

            if (!selectedTrack) {
                if (fetchToken !== this.captionFetchToken) return;
                console.log('No caption tracks available for this video');
                this.captions = null;
                this.showToast('No captions available for this video', 'info');
                document.getElementById('syncStatusText').textContent = 'No captions available';
                return;
            }

            const captions = await this.loadTimedTextTrack(videoId, selectedTrack);
            if (fetchToken !== this.captionFetchToken) return;

            if (captions.length > 0) {
                this.captions = captions;
                console.log(`Loaded ${captions.length} captions for video (${selectedTrack.languageCode || 'unknown'})`);
                this.showToast(`Captions loaded: ${captions.length} segments`, 'success');
                document.getElementById('syncStatusText').textContent = 'Ready to sync';

                // Render caption display area
                this.renderCaptionDisplay();
            } else {
                console.log('Caption track was found but had no usable segments');
                this.captions = null;
                this.showToast('No captions available for this video', 'info');
                document.getElementById('syncStatusText').textContent = 'No captions available';
            }
        } catch (error) {
            if (fetchToken !== this.captionFetchToken) return;
            console.error('Failed to fetch captions:', error);
            this.captions = null;
            this.showToast('Failed to load captions', 'error');
            document.getElementById('syncStatusText').textContent = 'Caption error';
        }
    }

    async fetchCaptionsForCurrentVideo() {
        if (!this.player || !this.isPlayerReady) return;
        const videoData = this.player.getVideoData ? this.player.getVideoData() : null;
        const videoId = videoData?.video_id;
        if (!videoId || videoId === 'placeholder_video_id') return;
        await this.fetchCaptions(videoId);
    }

    getCaptionTracksFromPlayer() {
        if (!this.player || !this.isPlayerReady) return [];
        try {
            if (typeof this.player.loadModule === 'function') {
                this.player.loadModule('captions');
            }
            if (typeof this.player.getOption === 'function') {
                const tracks = this.player.getOption('captions', 'tracklist');
                return Array.isArray(tracks) ? tracks : [];
            }
        } catch (error) {
            console.warn('Unable to access YouTube caption track list', error);
        }
        return [];
    }

    pickCaptionTrack(tracks) {
        if (!Array.isArray(tracks) || tracks.length === 0) return null;

        const englishCodes = ['en', 'en-US', 'en-GB'];
        const isEnglish = (track) => englishCodes.includes(track.languageCode);
        const isGenerated = (track) => track.kind === 'asr';

        const manualEnglish = tracks.find(track => isEnglish(track) && !isGenerated(track));
        if (manualEnglish) return manualEnglish;

        const generatedEnglish = tracks.find(track => isEnglish(track));
        if (generatedEnglish) return generatedEnglish;

        const manualAny = tracks.find(track => !isGenerated(track));
        if (manualAny) return manualAny;

        return tracks[0];
    }

    async loadTimedTextTrack(videoId, track) {
        const params = new URLSearchParams();
        params.set('v', videoId);
        params.set('fmt', 'json3');

        if (track.languageCode) {
            params.set('lang', track.languageCode);
        }
        if (track.kind) {
            params.set('kind', track.kind);
        }
        if (track.name) {
            params.set('name', track.name);
        }

        const timedTextUrl = `https://www.youtube.com/api/timedtext?${params.toString()}`;
        const response = await fetch(timedTextUrl);
        if (!response.ok) {
            throw new Error(`Caption request failed with status ${response.status}`);
        }

        const json = await response.json();
        return this.parseJson3Captions(json);
    }

    parseJson3Captions(json) {
        if (!json || !Array.isArray(json.events)) return [];

        const formattedCaptions = [];
        for (const event of json.events) {
            const startMs = Number(event.tStartMs);
            const durationMs = Number(event.dDurationMs);
            const segments = Array.isArray(event.segs) ? event.segs : [];

            if (!Number.isFinite(startMs) || startMs < 0) continue;

            const text = segments
                .map(seg => (seg && typeof seg.utf8 === 'string' ? seg.utf8 : ''))
                .join('')
                .replace(/\s+/g, ' ')
                .trim();

            if (!text) continue;

            const start = startMs / 1000;
            const duration = Number.isFinite(durationMs) && durationMs > 0 ? durationMs / 1000 : 2;
            const end = start + duration;

            const words = text.split(/\s+/).filter(Boolean);
            const wordDuration = words.length > 0 ? duration / words.length : 0;
            const wordTimings = words.map((word, idx) => {
                const wordStart = start + (idx * wordDuration);
                return {
                    text: word,
                    start: wordStart,
                    end: wordStart + wordDuration
                };
            });

            formattedCaptions.push({
                text,
                start,
                duration,
                end,
                words: wordTimings
            });
        }

        return formattedCaptions;
    }
    
    renderCaptionDisplay() {
        // Add a caption display overlay if it doesn't exist
        let captionDisplay = document.getElementById('captionDisplay');
        if (!captionDisplay) {
            const videoContainer = document.querySelector('.video-player');
            if (videoContainer) {
                captionDisplay = document.createElement('div');
                captionDisplay.id = 'captionDisplay';
                captionDisplay.className = 'caption-display';
                captionDisplay.innerHTML = '<span class="caption-text"></span>';
                //videoContainer.appendChild(captionDisplay);
            }
        }
    }
    
    getCurrentCaption(currentTime) {
        if (!this.captions) return null;
        
        for (let i = 0; i < this.captions.length; i++) {
            const caption = this.captions[i];
            if (currentTime >= caption.start && currentTime <= caption.end) {
                this.currentCaptionIndex = i;
                return caption;
            }
        }
        return null;
    }
    
    // Simplified caption-based sync
    syncWithCaptions(currentTime, duration) {
        const caption = this.getCurrentCaption(currentTime);
        const captionDisplay = document.querySelector('#captionDisplay .caption-text');
        const totalVerses = document.querySelectorAll('#syncVerses1 .sync-verse').length;
        if (totalVerses === 0) return;

        let matchedVerse = null;

        // Update caption display
        if (caption && captionDisplay) {
            if (this.lastCaptionText !== caption.text) {
                this.lastCaptionText = caption.text;
                captionDisplay.textContent = caption.text;
                captionDisplay.parentElement.classList.add('active');
            }
            // Find best matching verse for current caption
            matchedVerse = this.findBestMatchingVerse(caption.text);
            // Record the start time for this verse if matched via caption
            if (matchedVerse && !this.verseStartTimes.has(matchedVerse)) {
                this.verseStartTimes.set(matchedVerse, currentTime);
            }
        } else if (captionDisplay) {
            captionDisplay.parentElement.classList.remove('active');
            this.lastCaptionText = null;
        }

        // Fall back to time-based sync if no caption match
        if (!matchedVerse) {
            matchedVerse = this.getVerseByTime(currentTime, duration);
        }

        // Update verse highlight if changed
        if (matchedVerse && matchedVerse !== this.lastHighlightedVerse) {
            document.querySelectorAll('.sync-verse.active').forEach(el => {
                el.classList.remove('active');
            });
            document.querySelectorAll(`.sync-verse[data-verse="${matchedVerse}"]`).forEach(verse => {
                verse.classList.add('active');
            });
            this.lastHighlightedVerse = matchedVerse;
            this.scrollToVerse(matchedVerse);
        }

        // Highlight words in the active verse using the precise audio position
        this.highlightActiveWords(matchedVerse, caption, currentTime);
    }
    
    // Get verse based on time progression with dynamic adjustment
    getVerseByTime(currentTime, duration) {
        const totalVerses = document.querySelectorAll('#syncVerses1 .sync-verse').length;
        if (totalVerses === 0) return '1';
        
        // Use recorded verse start times for dynamic adjustment
        const knownVerses = Array.from(this.verseStartTimes.keys()).sort((a, b) => a - b);
        
        if (knownVerses.length >= 2) {
            // Find the last known verse before current time
            let lastKnownVerse = null;
            let lastKnownTime = 0;
            for (const verse of knownVerses) {
                const time = this.verseStartTimes.get(verse);
                if (time <= currentTime) {
                    lastKnownVerse = verse;
                    lastKnownTime = time;
                } else {
                    break;
                }
            }
            
            if (lastKnownVerse) {
                const nextKnownVerses = knownVerses.filter(v => v > lastKnownVerse);
                if (nextKnownVerses.length > 0) {
                    const nextVerse = nextKnownVerses[0];
                    const nextTime = this.verseStartTimes.get(nextVerse);
                    const timeDiff = nextTime - lastKnownTime;
                    const verseDiff = nextVerse - lastKnownVerse;
                    const timeSinceLast = currentTime - lastKnownTime;
                    
                    if (timeDiff > 0) {
                        const progressBetween = timeSinceLast / timeDiff;
                        const estimatedVerse = lastKnownVerse + (verseDiff * progressBetween);
                        return Math.max(1, Math.min(Math.round(estimatedVerse), totalVerses)).toString();
                    }
                } else {
                    // After last known verse, extrapolate based on average time per verse
                    const avgTimePerVerse = (lastKnownTime - (this.verseStartTimes.get(knownVerses[0]) || 0)) / (lastKnownVerse - 1);
                    if (avgTimePerVerse > 0) {
                        const versesSinceLast = (currentTime - lastKnownTime) / avgTimePerVerse;
                        const estimatedVerse = lastKnownVerse + versesSinceLast;
                        return Math.max(1, Math.min(Math.round(estimatedVerse), totalVerses)).toString();
                    }
                }
            }
        }
        
        // Fallback to linear time-based calculation
        const totalDuration = duration || 240;
        const introTime = 5;
        const outroTime = 10;
        const contentDuration = totalDuration - introTime - outroTime;
        
        const adjustedTime = Math.max(0, currentTime - introTime);
        const progress = Math.min(Math.max(adjustedTime / contentDuration, 0), 1);
        
        const estimatedVerse = Math.floor(progress * totalVerses) + 1;
        return Math.max(1, Math.min(estimatedVerse, totalVerses)).toString();
    }
    
    // Highlight matching words in the active verse, using per-word audio timings when present
    highlightActiveWords(verseNum, caption, currentTime) {
        document.querySelectorAll('.sync-word.caption-match, .sync-word.caption-match-strong').forEach(el => {
            el.classList.remove('caption-match', 'caption-match-strong');
        });

        if (!verseNum || !caption) return;

        // Build the set of caption words spoken so far (uses per-word timings when available)
        const cumulative = [];
        let currentNorm = null;
        const hasTimings = Array.isArray(caption.words) && caption.words.length > 0 && Number.isFinite(currentTime);

        if (hasTimings) {
            for (const w of caption.words) {
                const norm = this.normalizeText(w.text);
                if (!norm || norm.length < 2) continue;
                if (w.start <= currentTime + 0.1) {
                    cumulative.push(norm);
                    if (currentTime >= w.start && currentTime <= w.end + 0.05) {
                        currentNorm = norm;
                    }
                }
            }
        }
        if (cumulative.length === 0) {
            const all = this.normalizeText(caption.text).split(/\s+/).filter(w => w.length > 1);
            cumulative.push(...all);
        }
        if (cumulative.length === 0) return;

        const cumulativeSet = new Set(cumulative);
        const activeWordEls = document.querySelectorAll(`.sync-verse[data-verse="${verseNum}"] .sync-word`);

        activeWordEls.forEach(wordEl => {
            const wordText = this.normalizeText(wordEl.textContent);
            if (!wordText || wordText.length < 2) return;
            if (cumulativeSet.has(wordText)) {
                wordEl.classList.add('caption-match');
                return;
            }
            for (const cw of cumulative) {
                if (this.looseWordMatch(cw, wordText)) {
                    wordEl.classList.add('caption-match');
                    break;
                }
            }
        });

        if (currentNorm) {
            for (const wordEl of activeWordEls) {
                const wordText = this.normalizeText(wordEl.textContent);
                if (!wordText) continue;
                if (wordText === currentNorm || this.looseWordMatch(wordText, currentNorm)) {
                    wordEl.classList.add('caption-match-strong');
                    break;
                }
            }
        }
    }
    
    // Build a normalized, IDF-weighted index of verses for the current chapter (English column)
    buildVerseIndex(versesObj) {
        const byVerse = new Map();
        const docFreq = new Map();
        const verseNums = [];

        const ingest = (num, text) => {
            if (!Number.isFinite(num) || !text) return;
            const words = this.normalizeText(text).split(/\s+/).filter(w => w.length > 1);
            if (words.length === 0) return;
            const wordSet = new Set(words);
            byVerse.set(num, { words, wordSet });
            verseNums.push(num);
            wordSet.forEach(w => docFreq.set(w, (docFreq.get(w) || 0) + 1));
        };

        if (versesObj && typeof versesObj === 'object') {
            for (const [k, v] of Object.entries(versesObj)) {
                ingest(parseInt(k, 10), String(v));
            }
        } else {
            document.querySelectorAll('#syncVerses1 .sync-verse').forEach(el => {
                const num = parseInt(el.dataset.verse, 10);
                const text = el.textContent.replace(/^\s*\d+\s*/, '');
                ingest(num, text);
            });
        }

        if (verseNums.length === 0) {
            this.verseIndex = null;
            return;
        }

        const N = byVerse.size;
        const idf = new Map();
        docFreq.forEach((df, w) => {
            // Smoothed IDF; very common words trend toward ~0
            idf.set(w, Math.log(1 + N / df));
        });
        verseNums.sort((a, b) => a - b);
        this.verseIndex = { byVerse, idf, verseNums };
    }

    // Find the verse that best matches the caption text using IDF + locality + smoothing
    findBestMatchingVerse(captionText) {
        if (!captionText) return null;
        if (!this.verseIndex) this.buildVerseIndex();
        if (!this.verseIndex) return null;

        const captionWords = this.normalizeText(captionText)
            .split(/\s+/)
            .filter(w => w.length > 1);
        if (captionWords.length === 0) return null;

        const { byVerse, idf, verseNums } = this.verseIndex;
        if (verseNums.length === 0) return null;

        // Locality window around the last matched verse (audio progresses forward)
        const lastNum = parseInt(this.lastHighlightedVerse, 10);
        let candidates = verseNums;
        if (Number.isFinite(lastNum)) {
            const windowed = verseNums.filter(n => n >= lastNum - 2 && n <= lastNum + 6);
            if (windowed.length >= 3) candidates = windowed;
        }

        const weightOf = (w) => idf.get(w) ?? 0.4;
        const totalWeight = captionWords.reduce((s, w) => s + weightOf(w), 0) || 1;

        const scoreVerse = (num) => {
            const entry = byVerse.get(num);
            if (!entry) return 0;
            let matched = 0;
            for (const cw of captionWords) {
                const weight = weightOf(cw);
                if (entry.wordSet.has(cw)) {
                    matched += weight;
                } else if (this.fuzzyVerseHas(cw, entry.wordSet)) {
                    matched += weight * 0.4;
                }
            }
            return matched / totalWeight;
        };

        let bestNum = null;
        let bestScore = 0;
        for (const num of candidates) {
            let score = scoreVerse(num);
            if (Number.isFinite(lastNum)) {
                const delta = num - lastNum;
                if (delta === 0) score *= 1.10;
                else if (delta === 1) score *= 1.06;
                else if (delta === 2) score *= 1.02;
                else if (delta < 0) score *= 0.80;
                else if (delta > 4) score *= 0.90;
            }
            if (score > bestScore) {
                bestScore = score;
                bestNum = num;
            }
        }

        if (bestNum === null || bestScore < 0.18) return null;

        // Smoothing: keep recent matches and resist single-frame jumps
        this.recentVerseMatches.push(bestNum);
        if (this.recentVerseMatches.length > 4) this.recentVerseMatches.shift();

        if (Number.isFinite(lastNum) && bestNum !== lastNum) {
            const lastTwo = this.recentVerseMatches.slice(-2);
            const consistent = lastTwo.length === 2 && lastTwo[0] === lastTwo[1];
            if (bestScore < 0.42 && !consistent) {
                return this.lastHighlightedVerse;
            }
        }

        return bestNum.toString();
    }

    // Lightweight stem-prefix check for caption→verse fuzzy matching
    fuzzyVerseHas(captionWord, verseWordSet) {
        if (!captionWord || captionWord.length < 5) return false;
        const stem = captionWord.substring(0, 4);
        for (const vw of verseWordSet) {
            if (vw.length >= 4 && vw.startsWith(stem)) return true;
        }
        return false;
    }
    
    // Normalize text for matching (remove punctuation, lowercase)
    normalizeText(text) {
        // Normalize Unicode (NFKC), remove punctuation, diacritics, and trim
        let norm = text.normalize('NFKC')
            .replace(/[.,!?;:'"()[\]{}]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
        // Remove Hebrew diacritics (niqqud, cantillation)
        norm = norm.replace(/[\u0591-\u05C7]/g, '');
        // Lowercase for non-Hebrew, leave Hebrew as-is (no case)
        return norm.toLowerCase();
    }
    
    // Loose word matching - handles variations, stems, etc.
    looseWordMatch(word1, word2) {
        if (!word1 || !word2) return false;
        // Normalize both words (removes diacritics, punctuation, etc.)
        const w1 = this.normalizeText(word1);
        const w2 = this.normalizeText(word2);
        // Exact match
        if (w1 === w2) return true;
        // For Hebrew: allow loose match if one contains the other and both are at least 2 chars (Hebrew words are often short)
        const isHebrew = /[\u0590-\u05FF]/.test(w1) && /[\u0590-\u05FF]/.test(w2);
        if (isHebrew) {
            if (w1.length > 1 && w2.length > 1 && (w1.includes(w2) || w2.includes(w1))) return true;
        } else {
            // One contains the other (for prefixes/suffixes)
            if (w1.length > 3 && w2.length > 3 && (w1.includes(w2) || w2.includes(w1))) return true;
            // Common stem (first 4+ characters match)
            if (w1.length >= 4 && w2.length >= 4) {
                const stem1 = w1.substring(0, Math.min(4, w1.length));
                const stem2 = w2.substring(0, Math.min(4, w2.length));
                if (stem1 === stem2) return true;
            }
        }
        // Levenshtein distance for similar words (for both Hebrew and non-Hebrew)
        if (w1.length > 4 && w2.length > 4) {
            const distance = this.levenshteinDistance(w1, w2);
            const maxLen = Math.max(w1.length, w2.length);
            if (distance / maxLen < 0.25) return true; // Allow ~25% difference
        }
        return false;
    }
    
    // Calculate Levenshtein distance between two strings
    levenshteinDistance(s1, s2) {
        const m = s1.length;
        const n = s2.length;
        const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));
        
        for (let i = 0; i <= m; i++) dp[i][0] = i;
        for (let j = 0; j <= n; j++) dp[0][j] = j;
        
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                if (s1[i - 1] === s2[j - 1]) {
                    dp[i][j] = dp[i - 1][j - 1];
                } else {
                    dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
                }
            }
        }
        return dp[m][n];
    }
    
    // Smooth scroll to a verse
    scrollToVerse(verseNum) {
        const verse1 = document.querySelector(`#syncVerses1 .sync-verse[data-verse="${verseNum}"]`);
        const verse2 = document.querySelector(`#syncVerses2 .sync-verse[data-verse="${verseNum}"]`);
        
        const scrollOptions = {
            behavior: 'smooth',
            block: 'center'
        };
        
        if (verse1) verse1.scrollIntoView(scrollOptions);
        if (verse2) verse2.scrollIntoView(scrollOptions);
    }
    

    

    
    updateTimeDisplay() {
        if (!this.player || !this.isPlayerReady) return;
        
        const current = this.player.getCurrentTime() || 0;
        const duration = this.player.getDuration() || 0;
        
        const formatTime = (seconds) => {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        };
        
        document.getElementById('timeDisplay').textContent = 
            `${formatTime(current)} / ${formatTime(duration)}`;
    }

    // ===== Bible Search =====
    onSearchInput() {
        const input = document.getElementById('searchInput');
        const clearBtn = document.getElementById('searchClear');
        const query = input.value.trim();

        clearBtn.classList.toggle('hidden', query.length === 0);

        clearTimeout(this.searchDebounceTimer);
        if (query.length >= 2) {
            this.searchDebounceTimer = setTimeout(() => this.performSearch(), 400);
        } else {
            this.closeSearch();
        }
    }

    async performSearch() {
        const query = document.getElementById('searchInput').value.trim();
        if (query.length < 2) return;

        const translation = document.getElementById('searchTranslation').value;
        const container = document.getElementById('searchResultsContainer');
        const list = document.getElementById('searchResultsList');
        const countEl = document.getElementById('searchResultsCount');

        // Show loading
        container.classList.remove('hidden');
        list.innerHTML = '<div class="search-loading">Searching…</div>';
        countEl.textContent = '';

        try {
            const url = `/api/search?q=${encodeURIComponent(query)}&translation=${encodeURIComponent(translation)}&limit=100`;
            const resp = await fetch(url);
            const data = await resp.json();

            if (data.error) {
                list.innerHTML = `<div class="search-no-results">${data.error}</div>`;
                countEl.textContent = '';
                return;
            }

            if (data.count === 0) {
                list.innerHTML = '<div class="search-no-results">No results found</div>';
                countEl.textContent = '0 results';
                return;
            }

            countEl.textContent = `${data.count}${data.truncated ? '+' : ''} results`;

            list.innerHTML = '';
            data.results.forEach(r => {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                item.dataset.book = r.book;
                item.dataset.chapter = r.chapter;
                item.dataset.verse = r.verse;

                // Highlight the query in the snippet
                const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(`(${escapedQuery})`, 'gi');
                const highlighted = r.snippet.replace(regex, '<mark>$1</mark>');

                item.innerHTML = `
                    <div class="search-result-ref">
                        <span class="search-result-book">${r.book} ${r.chapter}:${r.verse}</span>
                        <span class="search-result-trans">${r.translation}</span>
                    </div>
                    <div class="search-result-text">${highlighted}</div>
                `;

                item.addEventListener('click', () => {
                    this.navigateToVerse(r.book, r.chapter, r.verse, query);
                });

                list.appendChild(item);
            });
        } catch (err) {
            list.innerHTML = '<div class="search-no-results">Search failed. Please try again.</div>';
            console.error('Search error:', err);
        }
    }

    navigateToVerse(book, chapter, verse, searchQuery = '') {
        this.currentBook = book;
        this.currentChapter = chapter;
        this.pendingHighlightVerse = verse;
        this.pendingSearchQuery = searchQuery;
        this.suppressAutoPlay = true;
        document.getElementById('bookSelect').value = book;
        this.loadChapters(book, chapter);
        this.closeSearch();
    }

    highlightPendingVerse() {
        const verse = this.pendingHighlightVerse;
        if (!verse) return;
        this.pendingHighlightVerse = null;

        // Small delay to ensure DOM is rendered
        setTimeout(() => {
            // Clear any existing search highlights
            document.querySelectorAll('.search-highlight').forEach(el => el.classList.remove('search-highlight'));

            // Find and highlight the verse in all visible views
            const selectors = [
                `.sync-verse[data-verse="${verse}"]`,
                `.verse[data-verse="${verse}"]`,
                `.parallel-verse[data-verse="${verse}"]`
            ];

            const query = this.pendingSearchQuery || '';
            this.pendingSearchQuery = null;

            // Track which scroll containers we've already scrolled so we
            // scroll once per container (each side of the reader).
            const scrolledContainers = new Set();

            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    el.classList.add('search-highlight');

                    // Highlight the matched search text within the verse
                    if (query) {
                        const escapedQ = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                        const re = new RegExp(`(${escapedQ})`, 'gi');
                        // Only process text nodes to avoid breaking HTML structure
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
                        const textNodes = [];
                        while (walker.nextNode()) textNodes.push(walker.currentNode);
                        textNodes.forEach(node => {
                            if (re.test(node.nodeValue)) {
                                const span = document.createElement('span');
                                span.innerHTML = node.nodeValue.replace(re, '<mark class="search-term">$1</mark>');
                                node.parentNode.replaceChild(span, node);
                            }
                        });
                    }

                    // Scroll each scrollable container to the highlighted verse
                    // independently, so both sides of the reader stay in sync.
                    const scrollParent = el.closest('.sync-verses, .parallel-column, .verses, .page-content');
                    const containerId = scrollParent ? (scrollParent.id || scrollParent.className) : '__default__';
                    if (!scrolledContainers.has(containerId)) {
                        scrolledContainers.add(containerId);
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                });
            });
        }, 300);
    }

    clearSearchHighlight() {
        document.querySelectorAll('.search-highlight').forEach(el => {
            // Remove inline <mark> tags, restoring original text
            el.querySelectorAll('mark.search-term').forEach(mark => {
                mark.replaceWith(mark.textContent);
            });
            el.classList.remove('search-highlight');
        });
    }

    clearSearch() {
        const input = document.getElementById('searchInput');
        input.value = '';
        document.getElementById('searchClear').classList.add('hidden');
        this.closeSearch();
    }

    closeSearch() {
        document.getElementById('searchResultsContainer').classList.add('hidden');
    }

    // ===== Mobile verse jump =====
    populateMobileVerseSelect() {
        const sel = document.getElementById('mobileVerseSelect');
        if (!sel) return;
        const verseNums = Object.keys(this.verses || {})
            .map(n => parseInt(n))
            .filter(n => !isNaN(n))
            .sort((a, b) => a - b);
        sel.innerHTML = '<option value="">Verse</option>' +
            verseNums.map(n => `<option value="${n}">v${n}</option>`).join('');
        // Mirror into the bottom-bar nav jump verse select if present
        const navSel = document.getElementById('navVerseSelect');
        if (navSel) {
            navSel.innerHTML = '<option value="">Verse</option>' +
                verseNums.map(n => `<option value="${n}">v${n}</option>`).join('');
        }
        this.updateNavJumpLabel();
    }

    setupNavJumpPopover() {
        const btn = document.getElementById('navJumpBtn');
        const pop = document.getElementById('navJumpPopover');
        const bookSel = document.getElementById('navBookSelect');
        const chapSel = document.getElementById('navChapterSelect');
        const verseSel = document.getElementById('navVerseSelect');
        if (!btn || !pop) return;

        const open = () => {
            // Sync chapter options from the mobile chapter select
            const mobileChap = document.getElementById('mobileChapterSelect');
            if (mobileChap && chapSel) {
                chapSel.innerHTML = mobileChap.innerHTML;
                chapSel.value = String(this.currentChapter || mobileChap.value || '1');
            }
            if (bookSel) bookSel.value = this.currentBook || bookSel.value;
            if (verseSel) verseSel.value = '';
            pop.classList.remove('hidden');
            btn.setAttribute('aria-expanded', 'true');
        };
        const close = () => {
            pop.classList.add('hidden');
            btn.setAttribute('aria-expanded', 'false');
        };

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (pop.classList.contains('hidden')) open(); else close();
        });
        pop.addEventListener('click', (e) => e.stopPropagation());
        document.addEventListener('click', () => {
            if (!pop.classList.contains('hidden')) close();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !pop.classList.contains('hidden')) close();
        });

        if (bookSel) {
            bookSel.addEventListener('change', (e) => {
                const mobileBook = document.getElementById('mobileBookSelect');
                if (mobileBook) {
                    mobileBook.value = e.target.value;
                    mobileBook.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }
        if (chapSel) {
            chapSel.addEventListener('change', (e) => {
                const mobileChap = document.getElementById('mobileChapterSelect');
                if (mobileChap) {
                    mobileChap.value = e.target.value;
                    mobileChap.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }
        if (verseSel) {
            verseSel.addEventListener('change', (e) => {
                const v = e.target.value;
                if (!v) return;
                this.scrollToVerse(parseInt(v));
                close();
            });
        }
    }

    updateNavJumpLabel() {
        const label = document.getElementById('navJumpLabel');
        if (!label) return;
        if (this.currentBook && this.currentChapter) {
            label.textContent = `${this.currentBook} ${this.currentChapter}`;
        }
    }

    scrollToVerse(verseNum) {
        if (!verseNum) return;
        const selectors = [
            `#syncVerses1 .sync-verse[data-verse="${verseNum}"]`,
            `#syncVerses2 .sync-verse[data-verse="${verseNum}"]`,
            `#col1Verses .parallel-verse[data-verse="${verseNum}"]`,
            `.verses .verse[data-verse="${verseNum}"]`
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.classList.add('active');
                setTimeout(() => el.classList.remove('active'), 1800);
                return;
            }
        }
    }

    
    // ===== Mobile sidebar/menu backdrop =====
    _syncSidebarBackdrop() {
        const backdrop = document.getElementById('sidebarBackdrop');
        if (!backdrop) return;
        const sidebar = document.getElementById('sidebar');
        const topNav = document.getElementById('topNav');
        const sidebarOpen = sidebar && sidebar.classList.contains('open');
        const navOpen = topNav && topNav.classList.contains('open');
        backdrop.classList.toggle('visible', !!(sidebarOpen || navOpen));
    }

    // ===== User Data: position, bookmarks, notes, highlights =====

    _currentViewName() {
        if (document.getElementById('videoView')?.classList.contains('active')) return 'video';
        if (document.getElementById('parallelView')?.classList.contains('active')) return 'parallel';
        return 'reader';
    }

    async _restoreReadingState() {
        if (!this.userData) return;
        try {
            const state = await this.userData.getReadingState();
            if (!state) return;
            const bookSelect = document.getElementById('bookSelect');
            const valid = bookSelect && Array.from(bookSelect.options).some(o => o.value === state.book);
            if (!valid) return;
            this.currentBook = state.book;
            this.currentChapter = Math.max(1, parseInt(state.chapter, 10) || 1);
            if (state.verse) this.pendingHighlightVerse = state.verse;
        } catch (e) {
            console.warn('restoreReadingState failed', e);
        }
    }

    setupUserDataUI() {
        if (!this.userData) return;

        const panel = document.getElementById('bookmarksPanel');
        const openBtn = document.getElementById('bookmarksBtn');
        const closeBtn = document.getElementById('bookmarksClose');
        if (openBtn && panel) {
            openBtn.addEventListener('click', () => {
                this._renderBookmarksList();
                panel.classList.add('open');
                panel.setAttribute('aria-hidden', 'false');
            });
        }
        if (closeBtn && panel) {
            closeBtn.addEventListener('click', () => {
                panel.classList.remove('open');
                panel.setAttribute('aria-hidden', 'true');
            });
        }

        // Right-click on a sync verse opens the action menu. Long-press
        // on touch devices does the same.
        document.addEventListener('contextmenu', (e) => {
            const verseEl = e.target.closest && e.target.closest('.sync-verse[data-verse], .parallel-verse[data-verse]');
            if (!verseEl) return;
            e.preventDefault();
            this._openVerseMenu(verseEl, e.clientX, e.clientY);
        });

        // Touch long-press → open menu. We track the starting point so
        // a small finger jitter does not cancel the press, and we
        // suppress the synthetic click that follows the long-press.
        let touchTimer = null;
        let touchStartX = 0, touchStartY = 0;
        let touchFired = false;
        const cancelTouch = () => {
            clearTimeout(touchTimer);
            touchTimer = null;
        };
        document.addEventListener('touchstart', (e) => {
            touchFired = false;
            const verseEl = e.target.closest && e.target.closest('.sync-verse[data-verse], .parallel-verse[data-verse]');
            if (!verseEl) return;
            const t = e.touches[0];
            touchStartX = t.clientX;
            touchStartY = t.clientY;
            cancelTouch();
            touchTimer = setTimeout(() => {
                touchFired = true;
                this._openVerseMenu(verseEl, touchStartX, touchStartY);
            }, 500);
        }, { passive: true });
        document.addEventListener('touchmove', (e) => {
            if (!touchTimer) return;
            const t = e.touches[0];
            // 10px jitter tolerance — beyond that, treat as a scroll.
            if (Math.abs(t.clientX - touchStartX) > 10 ||
                Math.abs(t.clientY - touchStartY) > 10) {
                cancelTouch();
            }
        }, { passive: true });
        document.addEventListener('touchend', cancelTouch);
        document.addEventListener('touchcancel', cancelTouch);
        // Suppress the synthetic click that fires ~300ms after a
        // long-press so it doesn't immediately close the menu we just
        // opened or trigger another handler.
        document.addEventListener('click', (e) => {
            if (touchFired) {
                touchFired = false;
                e.preventDefault();
                e.stopPropagation();
            }
        }, true);

        // Click on note indicator → open note editor
        document.addEventListener('click', (e) => {
            const indicator = e.target.closest && e.target.closest('.note-indicator');
            if (!indicator) return;
            e.preventDefault();
            e.stopPropagation();
            const verseEl = indicator.closest('[data-verse]');
            if (verseEl) this._openNoteEditor(parseInt(verseEl.dataset.verse, 10));
        });

        // Hide context menu on outside click / Escape
        const menu = document.getElementById('verseMenu');
        document.addEventListener('click', (e) => {
            if (menu && !menu.hidden && !menu.contains(e.target)) {
                menu.hidden = true;
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu && !menu.hidden) menu.hidden = true;
        });

        // Wire menu actions
        if (menu) {
            menu.addEventListener('click', async (e) => {
                const colorBtn = e.target.closest('[data-color]');
                if (colorBtn) {
                    const color = colorBtn.dataset.color || '';
                    await this._applyHighlight(this._menuVerse, color);
                    menu.hidden = true;
                    return;
                }
                const item = e.target.closest('[data-action]');
                if (!item) return;
                const action = item.dataset.action;
                menu.hidden = true;
                if (action === 'bookmark') await this._toggleBookmark(this._menuVerse);
                else if (action === 'note') this._openNoteEditor(this._menuVerse);
            });
        }

        // Note modal
        const overlay = document.getElementById('noteOverlay');
        const cancel = () => { if (overlay) overlay.hidden = true; };
        document.getElementById('noteCancel')?.addEventListener('click', cancel);
        document.getElementById('noteCancel2')?.addEventListener('click', cancel);
        document.getElementById('noteSave')?.addEventListener('click', async () => {
            const body = document.getElementById('noteBody').value;
            await this._saveNote(this._noteVerse, body);
            cancel();
        });
        document.getElementById('noteDelete')?.addEventListener('click', async () => {
            await this._saveNote(this._noteVerse, '');
            cancel();
        });
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) cancel();
            });
        }
    }

    _openVerseMenu(verseEl, x, y) {
        const verse = parseInt(verseEl.dataset.verse, 10);
        if (!verse) return;
        this._menuVerse = verse;
        const menu = document.getElementById('verseMenu');
        if (!menu) return;

        // Update bookmark label based on current state
        const bookmarked = this.userData.isBookmarked(this.currentBook, this.currentChapter, verse);
        const bmLabel = menu.querySelector('[data-label="bookmark"]');
        if (bmLabel) bmLabel.textContent = bookmarked ? 'Remove bookmark' : 'Bookmark verse';
        const noteLabel = menu.querySelector('[data-label="note"]');
        if (noteLabel) noteLabel.textContent = this.userData.getNote(verse) ? 'Edit note' : 'Add note';

        menu.hidden = false;
        // Position, keeping menu within viewport
        const r = menu.getBoundingClientRect();
        const maxX = window.innerWidth - r.width - 8;
        const maxY = window.innerHeight - r.height - 8;
        menu.style.left = Math.max(8, Math.min(x, maxX)) + 'px';
        menu.style.top  = Math.max(8, Math.min(y, maxY)) + 'px';
    }

    async _toggleBookmark(verse) {
        if (!verse) return;
        const existing = this.userData.bookmarks.find(b =>
            b.book === this.currentBook && b.chapter === this.currentChapter && +b.verse === +verse);
        if (existing) {
            await this.userData.removeBookmark(existing.id);
            this.showToast('Bookmark removed', 'info');
        } else {
            await this.userData.addBookmark(this.currentBook, this.currentChapter, verse, null);
            this.showToast('Bookmark added', 'success');
        }
        this._applyVerseAnnotations();
        this._renderBookmarksList();
    }

    async _applyHighlight(verse, color) {
        if (!verse) return;
        await this.userData.setHighlight(this.currentBook, this.currentChapter, verse, color);
        this._applyVerseAnnotations();
    }

    _openNoteEditor(verse) {
        if (!verse) return;
        this._noteVerse = verse;
        const overlay = document.getElementById('noteOverlay');
        const body = document.getElementById('noteBody');
        const title = document.getElementById('noteTitle');
        const del = document.getElementById('noteDelete');
        if (!overlay || !body) return;
        const existing = this.userData.getNote(verse);
        body.value = existing ? existing.body : '';
        if (title) title.textContent = `Note on ${this.currentBook} ${this.currentChapter}:${verse}`;
        if (del) del.style.display = existing ? '' : 'none';
        overlay.hidden = false;
        setTimeout(() => body.focus(), 30);
    }

    async _saveNote(verse, body) {
        if (!verse) return;
        await this.userData.setNote(this.currentBook, this.currentChapter, verse, body);
        this._applyVerseAnnotations();
    }

    _applyVerseAnnotations() {
        if (!this.userData) return;
        const sel = '.sync-verse[data-verse], .parallel-verse[data-verse]';
        document.querySelectorAll(sel).forEach((el) => {
            const v = parseInt(el.dataset.verse, 10);
            if (!v) return;
            // Highlight color
            const hl = this.userData.getHighlight(v);
            if (hl) el.setAttribute('data-hl', hl.color);
            else el.removeAttribute('data-hl');
            // Bookmark marker
            const bm = this.userData.isBookmarked(this.currentBook, this.currentChapter, v);
            if (bm) el.setAttribute('data-bookmarked', '1');
            else el.removeAttribute('data-bookmarked');
            // Note indicator
            el.querySelectorAll(':scope > .note-indicator').forEach(n => n.remove());
            const note = this.userData.getNote(v);
            if (note) {
                const ind = document.createElement('span');
                ind.className = 'note-indicator';
                ind.title = note.body.slice(0, 200);
                ind.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
                el.appendChild(ind);
            }
        });
    }

    _renderBookmarksList() {
        if (!this.userData) return;
        const list = document.getElementById('bookmarksList');
        if (!list) return;
        const items = this.userData.bookmarks;
        if (!items.length) {
            list.innerHTML = '<p class="ud-empty">No bookmarks yet. Right-click a verse and choose <strong>Bookmark</strong>.</p>';
            return;
        }
        list.innerHTML = items.map(b => `
            <div class="ud-bookmark" data-id="${b.id}" data-book="${b.book}" data-chapter="${b.chapter}" data-verse="${b.verse}">
                <div class="ud-bookmark-info">
                    <div class="ud-bookmark-ref">${b.book} ${b.chapter}:${b.verse}</div>
                    ${b.label ? `<div class="ud-bookmark-label">${this._escape(b.label)}</div>` : ''}
                </div>
                <button class="ud-bookmark-del" aria-label="Remove">×</button>
            </div>
        `).join('');
        list.querySelectorAll('.ud-bookmark').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.ud-bookmark-del')) {
                    const id = parseInt(el.dataset.id, 10);
                    this.userData.removeBookmark(id).then(() => {
                        this._renderBookmarksList();
                        this._applyVerseAnnotations();
                    });
                    return;
                }
                this._navigateToBookmark(el.dataset.book, parseInt(el.dataset.chapter, 10), parseInt(el.dataset.verse, 10));
            });
        });
    }

    _navigateToBookmark(book, chapter, verse) {
        this.pendingHighlightVerse = verse;
        document.getElementById('bookSelect').value = book;
        if (book !== this.currentBook) {
            this.loadChapters(book, chapter);
        } else {
            this.loadChapter(book, chapter);
        }
        const panel = document.getElementById('bookmarksPanel');
        if (panel) {
            panel.classList.remove('open');
            panel.setAttribute('aria-hidden', 'true');
        }
    }

    _escape(s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    // ===== Toast Notifications =====
    showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon;
        if (type === 'success') {
            icon = '<polyline points="20 6 9 17 4 12"/>';
        } else if (type === 'info') {
            icon = '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>';
        } else {
            icon = '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>';
        }
        
        toast.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${icon}
            </svg>
            <span>${message}</span>
        `;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Initialize when YouTube API is ready
function onYouTubeIframeAPIReady() {
    console.log('YouTube API Ready');
}

// ===== Theme Management =====
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Initialize theme on all pages
initTheme();

// Theme toggle event listener
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
});

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    // Hide images marked with [data-hide-on-error] when they fail to load.
    // Used on sub-pages that reference legacy external images which may
    // be unreachable (e.g. the original ritd.info host going offline).
    // We use a global handler instead of inline `onerror=` so it works
    // even with strict Content-Security-Policy and survives DOM cloning.
    // We also set a generous timeout so an image whose host hangs
    // (DNS pending forever) still gets hidden after a few seconds.
    document.querySelectorAll('img[data-hide-on-error]').forEach(img => {
        const hide = () => { img.style.display = 'none'; };
        if (img.complete && img.naturalWidth === 0) { hide(); return; }
        if (img.complete) return;
        let done = false;
        const finish = (failed) => {
            if (done) return;
            done = true;
            if (failed) hide();
        };
        img.addEventListener('error', () => finish(true), { once: true });
        img.addEventListener('load',  () => finish(false), { once: true });
        setTimeout(() => {
            if (done) return;
            finish(!(img.complete && img.naturalWidth > 0));
        }, 6000);
    });

    // app.js is included on every page (so the theme toggle, header
    // nav, etc. work everywhere), but the Bible reader UI only exists
    // on the home page. Bail out early on other pages so we don't
    // throw NPEs binding events to elements that don't exist.
    if (!document.getElementById('bookSelect')) return;
    window.bibleReader = new BibleReader();
});
