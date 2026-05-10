// ===== RITDorg first-time-user tutorial =====
// A lightweight, self-contained guided tour with a spotlight cut-out and
// animated tooltip card. Re-launchable from the "?" Help button in the header.

(function () {
    'use strict';

    const STORAGE_KEY = 'ritd_tutorial_seen_v1';

    const STEPS = [
        {
            title: 'Welcome to RITDorg',
            body:  'A quick 30-second tour to show you how to read, listen and compare Scripture. You can replay this tour anytime from the “?” button in the header.',
            target: null,
        },
        {
            title: 'Pick a book',
            body:  'Use the Book and Chapter selectors to jump anywhere in the Bible. On mobile, the same controls live in the top bar.',
            target: '.book-selector',
        },
        {
            title: 'Search the Scriptures',
            body:  'Type any phrase to search across translations. You can even search Hebrew text directly.',
            target: '.bible-search',
        },
        {
            title: 'Choose translations',
            body:  'Read two translations side-by-side. Use the swap buttons to flip them — either column can show Hebrew, NIV, ESV and more.',
            target: '.sync-translations',
        },
        {
            title: 'Listen along',
            body:  'Press play to hear the chapter narrated. Verses highlight in time with the audio.',
            target: '#playPauseBtn',
        },
        {
            title: 'Hide the Hebrew column',
            body:  'Tap the eye icon to hide or show the Hebrew column at any time.',
            target: '#hebrewToggleBtn',
        },
        {
            title: 'Focus mode',
            body:  'Distraction-free reading: hides the header and sidebar so you can stay in the Word.',
            target: '#focusModeBtn',
        },
        {
            title: "You're all set",
            body:  'Enjoy the journey through Scripture. May the Lord bless your study!',
            target: null,
        },
    ];

    function $(id) { return document.getElementById(id); }

    let stepIndex = 0;
    let resizeRaf = 0;

    function isReady() {
        return $('tutorialOverlay') && $('tutorialCard');
    }

    function show() {
        if (!isReady()) return;
        stepIndex = 0;
        const overlay = $('tutorialOverlay');
        overlay.classList.add('active');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('tutorial-open');
        renderStep();
        window.addEventListener('resize', onResize);
        window.addEventListener('scroll', onResize, { passive: true });
    }

    function hide() {
        const overlay = $('tutorialOverlay');
        if (!overlay) return;
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('tutorial-open');
        try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
        window.removeEventListener('resize', onResize);
        window.removeEventListener('scroll', onResize);
        if (resizeRaf) { cancelAnimationFrame(resizeRaf); resizeRaf = 0; }
        // Clear spotlight so a re-open animates back in cleanly
        const rect = $('tutorialSpotRect');
        if (rect) {
            rect.setAttribute('width', '0');
            rect.setAttribute('height', '0');
        }
    }

    function onResize() {
        if (resizeRaf) cancelAnimationFrame(resizeRaf);
        resizeRaf = requestAnimationFrame(positionForStep);
    }

    function renderStep() {
        const step = STEPS[stepIndex];
        if (!step) { hide(); return; }

        const titleEl = $('tutorialTitle');
        const bodyEl  = $('tutorialBody');
        const progEl  = $('tutorialProgress');
        const prevBtn = $('tutorialPrev');
        const nextBtn = $('tutorialNext');

        if (titleEl) titleEl.textContent = step.title;
        if (bodyEl)  bodyEl.textContent  = step.body;
        if (progEl)  progEl.textContent  = `Step ${stepIndex + 1} of ${STEPS.length}`;

        if (prevBtn) {
            prevBtn.disabled = stepIndex === 0;
            prevBtn.style.visibility = stepIndex === 0 ? 'hidden' : 'visible';
        }
        if (nextBtn) {
            nextBtn.textContent = stepIndex === STEPS.length - 1 ? 'Finish' : 'Next';
        }

        // Re-trigger card pop animation
        const card = $('tutorialCard');
        if (card) {
            card.classList.remove('pop');
            void card.offsetWidth;
            card.classList.add('pop');
        }

        positionForStep();
    }

    function positionForStep() {
        const overlay = $('tutorialOverlay');
        const mask    = $('tutorialMask');
        const rect    = $('tutorialSpotRect');
        const card    = $('tutorialCard');
        if (!overlay || !mask || !rect || !card) return;

        const vw = window.innerWidth;
        const vh = window.innerHeight;
        mask.setAttribute('width',  String(vw));
        mask.setAttribute('height', String(vh));

        const step = STEPS[stepIndex];
        const target = step && step.target ? document.querySelector(step.target) : null;

        if (!target) {
            // Center card; collapse spotlight to nothing.
            rect.setAttribute('width', '0');
            rect.setAttribute('height', '0');
            card.style.left = '50%';
            card.style.top  = '50%';
            card.style.transform = 'translate(-50%, -50%)';
            return;
        }

        // Make sure target is visible if scrollable; gently scroll into view.
        try {
            target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
        } catch {}

        const r = target.getBoundingClientRect();
        const pad = 10;
        const x = Math.max(0, r.left - pad);
        const y = Math.max(0, r.top  - pad);
        const w = Math.min(vw, r.width  + pad * 2);
        const h = Math.min(vh, r.height + pad * 2);

        rect.setAttribute('x', String(x));
        rect.setAttribute('y', String(y));
        rect.setAttribute('width',  String(w));
        rect.setAttribute('height', String(h));

        // Position the card: prefer below the target, fall back to above, else right/left.
        const cardW = Math.min(360, vw - 24);
        const cardH = card.offsetHeight || 200;
        const margin = 16;

        let cx, cy, transform = 'none';
        const spaceBelow = vh - (y + h);
        const spaceAbove = y;

        if (spaceBelow >= cardH + margin || spaceBelow >= spaceAbove) {
            // Below
            cx = Math.min(Math.max(8, r.left + r.width / 2 - cardW / 2), vw - cardW - 8);
            cy = Math.min(vh - cardH - 8, y + h + margin);
        } else {
            // Above
            cx = Math.min(Math.max(8, r.left + r.width / 2 - cardW / 2), vw - cardW - 8);
            cy = Math.max(8, y - cardH - margin);
        }

        card.style.width = cardW + 'px';
        card.style.left  = cx + 'px';
        card.style.top   = cy + 'px';
        card.style.transform = transform;
    }

    function next() {
        if (stepIndex >= STEPS.length - 1) { hide(); return; }
        stepIndex++;
        renderStep();
    }
    function prev() {
        if (stepIndex <= 0) return;
        stepIndex--;
        renderStep();
    }

    function bind() {
        const helpBtn = $('helpBtn');
        if (helpBtn) helpBtn.addEventListener('click', show);

        const nextBtn = $('tutorialNext');
        const prevBtn = $('tutorialPrev');
        const skipBtn = $('tutorialSkip');
        if (nextBtn) nextBtn.addEventListener('click', next);
        if (prevBtn) prevBtn.addEventListener('click', prev);
        if (skipBtn) skipBtn.addEventListener('click', hide);

        document.addEventListener('keydown', (e) => {
            if (!document.body.classList.contains('tutorial-open')) return;
            if (e.key === 'Escape') hide();
            else if (e.key === 'ArrowRight' || e.key === 'Enter') next();
            else if (e.key === 'ArrowLeft') prev();
        });

        // Click on the dim area (outside the card) advances the tour.
        const overlay = $('tutorialOverlay');
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay || e.target.id === 'tutorialMask') next();
            });
        }
    }

    function maybeAutoStart() {
        let seen = '0';
        try { seen = localStorage.getItem(STORAGE_KEY) || '0'; } catch {}
        if (seen !== '1') {
            // Wait a beat so the page lays out and elements have positions.
            setTimeout(show, 700);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => { bind(); maybeAutoStart(); });
    } else {
        bind();
        maybeAutoStart();
    }
})();
