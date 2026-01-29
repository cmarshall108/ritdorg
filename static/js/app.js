// ===== RITDorg - Interactive Bible Reader =====

class BibleReader {
        // Get the match score for a specific verse number and caption text
        getVerseMatchScore(verseNum, captionText) {
            if (!captionText || !verseNum) return 0;
            const allVerses = [
                ...document.querySelectorAll('#syncVerses1 .sync-verse'),
                ...document.querySelectorAll('#syncVerses2 .sync-verse')
            ];
            let combinedText = '';
            allVerses.forEach(verse => {
                if (verse.dataset.verse === verseNum) {
                    combinedText += ' ' + verse.textContent;
                }
            });
            if (!combinedText) return 0;
            const verseWords = this.normalizeText(combinedText).split(/\s+/).filter(w => w.length > 1);
            const captionWords = this.normalizeText(captionText).split(/\s+/).filter(w => w.length > 1);
            if (captionWords.length === 0) return 0;
            let matchCount = 0;
            captionWords.forEach(cw => {
                if (verseWords.some(vw => this.looseWordMatch(cw, vw))) {
                    matchCount++;
                }
            });
            return matchCount / captionWords.length;
        }
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
        
        // Video sync translations (Hebrew audio, show NIV + Hebrew text)
        this.syncTrans1 = 'NIV';
        this.syncTrans2 = 'Hebrew';
        
        // Video sync
        this.player = null;
        this.isPlayerReady = false;
        this.syncData = null;
        this.syncInterval = null;
        
        // Dynamic caption sync
        this.captions = null;
        this.currentCaptionIndex = -1;
        this.captionSyncEnabled = true;
        this.lastHighlightedVerse = null;
        this.lastCaptionText = null;
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        
        // Set dropdown to match default book
        document.getElementById('bookSelect').value = this.currentBook;
        
        this.initTheme();
        
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
            this.loadParallelVerses();
        });
        
        document.getElementById('parallelTrans2').addEventListener('change', (e) => {
            this.parallelTrans2 = e.target.value;
            this.loadParallelVerses();
        });
        
        // Swap translations button
        document.getElementById('swapTranslations').addEventListener('click', () => {
            const temp = this.parallelTrans1;
            this.parallelTrans1 = this.parallelTrans2;
            this.parallelTrans2 = temp;
            document.getElementById('parallelTrans1').value = this.parallelTrans1;
            document.getElementById('parallelTrans2').value = this.parallelTrans2;
            this.loadParallelVerses();
        });
        
        // Sync translation selectors
        document.getElementById('syncTrans1').addEventListener('change', (e) => {
            this.syncTrans1 = e.target.value;
            this.loadVideoSync();
        });
        
        document.getElementById('syncTrans2').addEventListener('change', (e) => {
            this.syncTrans2 = e.target.value;
            this.loadVideoSync();
        });
        
        // Font size
        document.querySelectorAll('.size-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.setFontSize(btn.dataset.size);
            });
        });
        
        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());
        
        // Video controls
        document.getElementById('playPauseBtn').addEventListener('click', () => this.togglePlay());
        document.querySelector('.progress-bar').addEventListener('click', (e) => this.seekVideo(e));
        
        // Video visibility toggle
        document.getElementById('videoToggleBtn').addEventListener('click', () => this.toggleVideoVisibility());
        
        // Chapter navigation
        document.getElementById('prevChapterBtn').addEventListener('click', () => this.prevChapter());
        document.getElementById('nextChapterBtn').addEventListener('click', () => this.nextChapter());
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
    
    async loadChapters(book, selectChapter = 1) {
        try {
            const response = await fetch(`/api/chapters/${book}`);
            const chapters = await response.json();
            
            const select = document.getElementById('chapterSelect');
            select.innerHTML = chapters.map(ch => 
                `<option value="${ch}" ${ch === selectChapter ? 'selected' : ''}>Chapter ${ch}</option>`
            ).join('');
            
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
                this.loadVideoSync();
            }
            
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
        readerView.classList.remove('font-small', 'font-medium', 'font-large');
        readerView.classList.add(`font-${size}`);
        
        // Apply to video view (Watch & Listen)
        const videoView = document.getElementById('videoView');
        videoView.classList.remove('font-small', 'font-medium', 'font-large');
        videoView.classList.add(`font-${size}`);
        
        // Apply to parallel view
        const parallelView = document.getElementById('parallelView');
        parallelView.classList.remove('font-small', 'font-medium', 'font-large');
        parallelView.classList.add(`font-${size}`);
    }
    
    // ===== Theme =====
    initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    }
    
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    }
    
    // ===== Parallel Translation View =====
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
                this.showToast(`${fallbackMsg.join(' and ')} not available. Showing KJV fallback.`, 'info');
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
        
        const syncScroll = (source, target) => {
            if (isSyncing) return;
            isSyncing = true;
            
            const scrollRatio = source.scrollTop / (source.scrollHeight - source.clientHeight);
            target.scrollTop = scrollRatio * (target.scrollHeight - target.clientHeight);
            
            requestAnimationFrame(() => { isSyncing = false; });
        };
        
        col1.addEventListener('scroll', () => syncScroll(col1, col2));
        col2.addEventListener('scroll', () => syncScroll(col2, col1));
    }
    
    // ===== Video Sync =====
    async loadVideoSync() {
        try {
            // Reset sync tracking for new chapter
            this.lastHighlightedVerse = null;
            
            const response = await fetch(`/api/sync/${this.currentBook}/${this.currentChapter}`);
            this.syncData = await response.json();
            
            document.getElementById('syncBookChapter').textContent = `${this.currentBook} ${this.currentChapter}`;
            document.getElementById('syncColName1').textContent = this.syncTrans1;
            document.getElementById('syncColName2').textContent = this.syncTrans2;
            
            if (this.syncData.video_id || this.syncData.playlist_id) {
                // Use playlist if available, otherwise fall back to video_id
                const playlistId = this.syncData.playlist_id || null;
                const playlistIndex = this.syncData.playlist_index || 0;
                this.initYouTubePlayer(this.syncData.video_id, playlistId, playlistIndex);
                this.renderSyncText();
                document.querySelector('.video-placeholder').style.display = 'none';
                
                // Fetch dynamic captions from YouTube
                if (this.syncData.video_id) {
                    this.fetchCaptions(this.syncData.video_id);
                }
                
                // Show playlist info if available
                if (playlistId) {
                    console.log(`Loading from RITDorg playlist: ${playlistId}, video index: ${playlistIndex}`);
                }
            } else {
                document.querySelector('.video-placeholder').style.display = 'flex';
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
        
        const syncScroll = (source, target) => {
            if (isSyncing) return;
            isSyncing = true;
            
            const scrollRatio = source.scrollTop / (source.scrollHeight - source.clientHeight);
            target.scrollTop = scrollRatio * (target.scrollHeight - target.clientHeight);
            
            requestAnimationFrame(() => { isSyncing = false; });
        };
        
        col1.addEventListener('scroll', () => syncScroll(col1, col2));
        col2.addEventListener('scroll', () => syncScroll(col2, col1));
    }
    
    initYouTubePlayer(videoId, playlistId = null, playlistIndex = 0) {
        // If player exists, load new video or playlist
        if (this.player && this.isPlayerReady) {
            if (playlistId) {
                // Use cuePlaylist then playVideoAt for better control
                this.player.cuePlaylist({
                    list: playlistId,
                    listType: 'playlist',
                    index: playlistIndex
                });
                // Give it a moment then start playing
                setTimeout(() => {
                    if (this.player) {
                        this.player.playVideoAt(playlistIndex);
                    }
                }, 500);
            } else if (videoId) {
                this.player.loadVideoById(videoId);
            }
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
            'rel': 0
        };
        
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
                },
                'onStateChange': (e) => this.onPlayerStateChange(e)
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
        
        const state = this.player.getPlayerState();
        if (state === YT.PlayerState.PLAYING) {
            this.player.pauseVideo();
        } else {
            this.player.playVideo();
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
        try {
            const response = await fetch(`/api/captions/${videoId}`);
            const data = await response.json();
            
            if (data.success && data.captions) {
                this.captions = data.captions;
                console.log(`Loaded ${data.captions.length} captions for video (${data.language}, ${data.is_generated ? 'auto-generated' : 'manual'})`);
                this.showToast(`Captions loaded: ${data.captions.length} segments`, 'success');
                
                // Render caption display area
                this.renderCaptionDisplay();
            } else {
                console.log('No captions available:', data.error);
                this.captions = null;
            }
        } catch (error) {
            console.error('Failed to fetch captions:', error);
            this.captions = null;
        }
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

        // Highlight words in the active verse
        this.highlightActiveWords(matchedVerse, caption);
    }
    
    // Get verse based on time progression
    getVerseByTime(currentTime, duration) {
        const totalVerses = document.querySelectorAll('#syncVerses1 .sync-verse').length;
        if (totalVerses === 0) return '1';
        
        const totalDuration = duration || 240;
        const introTime = 5; // Fixed intro time
        const outroTime = 10;
        const contentDuration = totalDuration - introTime - outroTime;
        
        const adjustedTime = Math.max(0, currentTime - introTime);
        const progress = Math.min(Math.max(adjustedTime / contentDuration, 0), 1);
        
        const estimatedVerse = Math.floor(progress * totalVerses) + 1;
        return Math.max(1, Math.min(estimatedVerse, totalVerses)).toString();
    }
    
    // Highlight matching words in the active verse
    highlightActiveWords(verseNum, caption) {
        // Clear previous highlights
        document.querySelectorAll('.sync-word.caption-match, .sync-word.caption-match-strong').forEach(el => {
            el.classList.remove('caption-match', 'caption-match-strong');
        });
        
        if (!verseNum || !caption) return;
        
        // Get caption words
        let captionWords = [];
        if (caption.words && caption.words.length > 0) {
            captionWords = caption.words.map(w => w.text);
        } else {
            captionWords = this.normalizeText(caption.text).split(/\s+/).filter(w => w.length > 1);
        }
        
        if (captionWords.length === 0) return;
        
        // Highlight matching words in the active verse
        document.querySelectorAll('.sync-word').forEach(wordEl => {
            const wordText = this.normalizeText(wordEl.textContent);
            const parentVerse = wordEl.closest('.sync-verse');
            const isActiveVerse = parentVerse?.dataset.verse === verseNum;
            
            if (!isActiveVerse) return;
            
            if (captionWords.some(cw => this.looseWordMatch(cw, wordText))) {
                wordEl.classList.add('caption-match');
            }
        });
    }
    
    // Find the verse that best matches the caption text
    findBestMatchingVerse(captionText) {
        if (!captionText) return null;
        const captionWords = this.normalizeText(captionText).split(/\s+/).filter(w => w.length > 1);
        if (captionWords.length === 0) return null;
        let bestMatch = null;
        let bestScore = 0;
        // Check BOTH columns - NIV (syncVerses1) and Hebrew (syncVerses2)
        const allVerses = [
            ...document.querySelectorAll('#syncVerses1 .sync-verse'),
            ...document.querySelectorAll('#syncVerses2 .sync-verse')
        ];
        // Group by verse number
        const verseTexts = new Map();
        allVerses.forEach(verse => {
            const verseNum = verse.dataset.verse;
            if (!verseTexts.has(verseNum)) {
                verseTexts.set(verseNum, '');
            }
            verseTexts.set(verseNum, verseTexts.get(verseNum) + ' ' + verse.textContent);
        });
        verseTexts.forEach((combinedText, verseNum) => {
            const verseWords = this.normalizeText(combinedText).split(/\s+/).filter(w => w.length > 1);
            // Calculate match score
            let matchCount = 0;
            captionWords.forEach(cw => {
                if (verseWords.some(vw => this.looseWordMatch(cw, vw))) {
                    matchCount++;
                }
            });
            const score = matchCount / captionWords.length;
            // Require at least 50% match for closer sync
            if (score > bestScore && score > 0.5) {
                bestScore = score;
                bestMatch = verseNum;
            }
        });
        return bestMatch;
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

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.bibleReader = new BibleReader();
});
