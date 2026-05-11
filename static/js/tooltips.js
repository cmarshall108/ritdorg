// ===== Hover captions (desktop only) =====
// Mirrors the native `title` attribute to a `data-tip` attribute on
// devices that have a real hover-capable pointer (i.e. mice/trackpads).
// CSS in style.css renders a styled caption above the element. We strip
// the native `title` so the OS tooltip doesn't double-up. Touch devices
// keep the native `title` for assistive tech but no caption pops up,
// so taps still feel snappy on phones/tablets.

(function () {
    'use strict';

    const SUPPORTS_HOVER =
        window.matchMedia &&
        window.matchMedia('(hover: hover) and (pointer: fine)').matches;

    if (!SUPPORTS_HOVER) return;

    const SKIP_TAGS = new Set(['IFRAME', 'IMG']);

    function captionize(el) {
        if (!el || el.nodeType !== 1) return;
        if (SKIP_TAGS.has(el.tagName)) return;
        if (el.dataset.tip) return;
        const t = el.getAttribute('title');
        if (!t) return;
        el.setAttribute('data-tip', t);
        // Stash the original title so screen readers / debugging can still
        // recover it, but remove the live attribute to suppress the OS popup.
        el.setAttribute('data-tip-orig', t);
        el.removeAttribute('title');
    }

    function scan(root) {
        if (!root || !root.querySelectorAll) return;
        if (root.nodeType === 1 && root.hasAttribute('title')) captionize(root);
        const els = root.querySelectorAll('[title]');
        for (let i = 0; i < els.length; i++) captionize(els[i]);
    }

    function start() {
        scan(document.body);
        const mo = new MutationObserver((mutations) => {
            for (const m of mutations) {
                if (m.type === 'childList') {
                    m.addedNodes.forEach(scan);
                } else if (m.type === 'attributes' && m.attributeName === 'title') {
                    captionize(m.target);
                }
            }
        });
        mo.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['title'],
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
