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
        
        this.init();
    }
    
    init() {
        this.searchDebounceTimer = null;
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
        
        // Load chapters for the book (this will also load chapter content and video sync)
        this.loadChapters(this.currentBook, this.currentChapter);
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
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
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
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
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
        
        // Swap translations button (disabled since Hebrew is locked to right side)
        const swapBtn = document.getElementById('swapTranslations');
        swapBtn.disabled = true;
        swapBtn.style.opacity = '0.5';
        swapBtn.style.cursor = 'not-allowed';
        swapBtn.title = 'Swap disabled - Hebrew is locked to right side';
        
        // Sync translation selectors
        document.getElementById('syncTrans1').addEventListener('change', (e) => {
            this.syncTrans1 = e.target.value;
            this.loadVideoSync();
        });
        
        // syncTrans2 is locked to Hebrew and cannot be changed
        // Ensure it's always set to Hebrew
        this.syncTrans2 = 'Hebrew';
        const syncTrans2Select = document.getElementById('syncTrans2');
        if (syncTrans2Select) {
            syncTrans2Select.value = 'Hebrew';
            syncTrans2Select.disabled = true;
        }
        
        // Filter syncTrans1 options to exclude Hebrew
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

        const focusModeBtn = document.getElementById('focusModeBtn');
        if (focusModeBtn) {
            focusModeBtn.addEventListener('click', () => this.toggleFocusMode());
        }
        
        // Chapter navigation
        document.getElementById('prevChapterBtn').addEventListener('click', () => this.prevChapter());
        document.getElementById('nextChapterBtn').addEventListener('click', () => this.nextChapter());

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
            const response = await fetch(`/api/verses/${book}/${chapter}?translation=${this.currentTranslation}`);
            const data = await response.json();
            
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
            
        } catch (error) {
            console.error('Failed to load verses:', error);
            this.showToast('Failed to load verses', 'error');
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
        
        return verseNums.map(num => `
            <p class="verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                ${this.verses[num]}
            </p>
        `).join('');
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
    
    // Update translation dropdown options to lock Hebrew to right side
    updateTranslationOptions() {
        const trans1Select = document.getElementById('parallelTrans1');
        const trans2Select = document.getElementById('parallelTrans2');
        
        // If we haven't stored all translations yet, get them from the current options
        if (this.allTranslations.length === 0) {
            this.allTranslations = Array.from(trans1Select.options).map(option => ({
                value: option.value,
                text: option.text
            }));
        }
        
        // Separate Hebrew and non-Hebrew translations
        const hebrewTranslations = this.allTranslations.filter(trans => 
            trans.value.toLowerCase().includes('hebrew')
        );
        const otherTranslations = this.allTranslations.filter(trans => 
            !trans.value.toLowerCase().includes('hebrew')
        );
        
        // Clear both selects
        trans1Select.innerHTML = '';
        trans2Select.innerHTML = '';
        
        // Populate left side (trans1) with non-Hebrew translations
        otherTranslations.forEach(trans => {
            const option = document.createElement('option');
            option.value = trans.value;
            option.text = trans.text;
            if (trans.value === this.parallelTrans1) {
                option.selected = true;
            }
            trans1Select.appendChild(option);
        });
        
        // Populate right side (trans2) with Hebrew translations
        hebrewTranslations.forEach(trans => {
            const option = document.createElement('option');
            option.value = trans.value;
            option.text = trans.text;
            if (trans.value === this.parallelTrans2) {
                option.selected = true;
            }
            trans2Select.appendChild(option);
        });
        
        // If no Hebrew translation is selected on the right, select the first available
        if (hebrewTranslations.length > 0 && !hebrewTranslations.some(trans => trans.value === this.parallelTrans2)) {
            this.parallelTrans2 = hebrewTranslations[0].value;
            trans2Select.value = this.parallelTrans2;
        }
    }
    
    // Update sync translation dropdown options to exclude Hebrew from left side
    updateSyncTranslationOptions() {
        const syncTrans1Select = document.getElementById('syncTrans1');
        
        // If we haven't stored all translations yet, get them from the current options
        if (this.allTranslations.length === 0) {
            this.allTranslations = Array.from(syncTrans1Select.options).map(option => ({
                value: option.value,
                text: option.text
            }));
        }
        
        // Clear syncTrans1
        syncTrans1Select.innerHTML = '';
        
        // Populate syncTrans1 with all translations except Hebrew
        this.allTranslations.forEach(trans => {
            if (!trans.value.toLowerCase().includes('hebrew')) {
                const option = document.createElement('option');
                option.value = trans.value;
                option.text = trans.text;
                if (trans.value === this.syncTrans1) {
                    option.selected = true;
                }
                syncTrans1Select.appendChild(option);
            }
        });
        
        // If current selection is Hebrew, switch to first available option
        if (this.syncTrans1.toLowerCase().includes('hebrew')) {
            const firstOption = syncTrans1Select.querySelector('option');
            if (firstOption) {
                this.syncTrans1 = firstOption.value;
                firstOption.selected = true;
            }
        }
    }
    
    async loadParallelVerses() {
        try {
            const response = await fetch(
                `/api/verses/parallel/${this.currentBook}/${this.currentChapter}?translation1=${this.parallelTrans1}&translation2=${this.parallelTrans2}`
            );
            const data = await response.json();
            
            this.parallelVerses1 = data.translation1.verses;
            this.parallelVerses2 = data.translation2.verses;
            
            // Update header with actual translation (shows fallback if applicable)
            document.getElementById('parallelBookChapter').textContent = `${this.currentBook} ${this.currentChapter}`;
            
            // Show actual translation name, with fallback indicator if needed
            const trans1Label = data.translation1.fallback 
                ? `${this.parallelTrans1} → ${data.translation1.actual}` 
                : this.parallelTrans1;
            const trans2Label = data.translation2.fallback 
                ? `${this.parallelTrans2} → ${data.translation2.actual}` 
                : this.parallelTrans2;
            
            document.getElementById('col1TransName').textContent = trans1Label;
            document.getElementById('col2TransName').textContent = trans2Label;
            
            // Show toast if either translation fell back
            if (data.translation1.fallback || data.translation2.fallback) {
                const fallbackMsg = [];
                if (data.translation1.fallback) fallbackMsg.push(`${this.parallelTrans1}`);
                if (data.translation2.fallback) fallbackMsg.push(`${this.parallelTrans2}`);
                this.showToast(`${fallbackMsg.join(' and ')} not available. Showing NIV fallback.`, 'info');
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
        
        container.innerHTML = verseNums.map(num => `
            <div class="parallel-verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                <span class="verse-text">${verses[num]}</span>
            </div>
        `).join('');
        
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
        let isSyncing = false;
        let manualScroll = false;
        let scrollTimer;
        
        const syncScroll = (source, target) => {
            if (isSyncing || manualScroll) return;
            isSyncing = true;
            
            const scrollRatio = source.scrollTop / (source.scrollHeight - source.clientHeight);
            target.scrollTop = scrollRatio * (target.scrollHeight - target.clientHeight);
            
            requestAnimationFrame(() => { isSyncing = false; });
        };
        
        const onScroll = () => {
            manualScroll = true;
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => { manualScroll = false; }, 300);
        };
        
        col1.addEventListener('scroll', onScroll);
        col2.addEventListener('scroll', onScroll);
        
        // Also sync on scroll
        col1.addEventListener('scroll', () => syncScroll(col1, col2));
        col2.addEventListener('scroll', () => syncScroll(col2, col1));
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
                
                // Fetch dynamic captions from YouTube for verse sync
                if (videoId && videoId !== 'placeholder_video_id') {
                    this.fetchCaptions(videoId);
                }
                
                console.log(`Loading video: ${videoId || 'playlist'}, playlist: ${playlistId}, index: ${playlistIndex}`);
            } else {
                document.querySelector('.video-placeholder').style.display = 'flex';
                document.getElementById('syncStatusText').textContent = 'No video available';
                this.renderSyncTextNoVideo();
            }
        } catch (error) {
            console.error('Failed to load sync data:', error);
        }
    }
    
    async renderSyncText() {
        // Fetch both translations for sync view
        const [response1, response2] = await Promise.all([
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans1}`),
            fetch(`/api/verses/${this.currentBook}/${this.currentChapter}?translation=${this.syncTrans2}`)
        ]);
        
        const data1 = await response1.json();
        const data2 = await response2.json();
        
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
        
        // Render first translation with word highlighting
        syncVerses1.innerHTML = this.renderSyncVerses(verses1, true);
        
        // Render second translation 
        syncVerses2.innerHTML = this.renderSyncVerses(verses2, false);
        
        // Build the searchable verse index used by caption matching
        this.buildVerseIndex(verses1);

        // Setup synchronized scrolling between sync columns
        this.setupSyncColumnScroll();
    }
    
    renderSyncVerses(verses, withWordSync) {
        const verseNums = Object.keys(verses).map(Number).sort((a, b) => a - b);
        
        return verseNums.map(verseNum => {
            const verseText = verses[verseNum];
            
            // Always wrap words in spans for dynamic highlighting
            const words = verseText.split(' ');
            const wordSpans = words.map((word, idx) => {
                return `<span class="sync-word">${word}</span>`;
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
        
        const syncVerses1 = document.getElementById('syncVerses1');
        const syncVerses2 = document.getElementById('syncVerses2');
        
        syncVerses1.innerHTML = this.renderSimpleVerses(verses1);
        syncVerses2.innerHTML = this.renderSimpleVerses(verses2);
        
        this.setupSyncColumnScroll();
    }
    
    renderSimpleVerses(verses) {
        const verseNums = Object.keys(verses).map(Number).sort((a, b) => a - b);
        
        return verseNums.map(num => `
            <p class="sync-verse" data-verse="${num}">
                <span class="verse-num">${num}</span>
                ${verses[num]}
            </p>
        `).join('');
    }
    
    setupSyncColumnScroll() {
        const col1 = document.getElementById('syncVerses1');
        const col2 = document.getElementById('syncVerses2');
        let isSyncing = false;
        let manualScroll = false;
        let scrollTimer;
        
        const syncScroll = (source, target) => {
            if (isSyncing || manualScroll) return;
            isSyncing = true;
            
            const scrollRatio = source.scrollTop / (source.scrollHeight - source.clientHeight);
            target.scrollTop = scrollRatio * (target.scrollHeight - target.clientHeight);
            
            requestAnimationFrame(() => { isSyncing = false; });
        };
        
        const onScroll = () => {
            manualScroll = true;
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => { manualScroll = false; }, 300);
        };
        
        col1.addEventListener('scroll', onScroll);
        col2.addEventListener('scroll', onScroll);
        
        // Also sync on scroll
        col1.addEventListener('scroll', () => syncScroll(col1, col2));
        col2.addEventListener('scroll', () => syncScroll(col2, col1));
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
        }
    }
    
    togglePlay() {
        if (!this.player || !this.isPlayerReady) return;
        this.clearSearchHighlight();
        
        const state = this.player.getPlayerState();
        if (state === YT.PlayerState.PLAYING) {
            this.player.pauseVideo();
        } else {
            this.player.playVideo();
        }
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
    window.bibleReader = new BibleReader();
});
