/* Optional email-capture prompt — dismissible, mobile-friendly. */
(function () {
    var el = document.getElementById('emailPrompt');
    if (!el) return;

    var form = document.getElementById('emailPromptForm');
    var status = el.querySelector('.email-prompt__status');
    var input = form.querySelector('input[name="email"]');

    function setStatus(msg, ok) {
        status.textContent = msg || '';
        status.className = 'email-prompt__status' + (ok ? ' ok' : (msg ? ' err' : ''));
    }

    function hide() {
        el.classList.add('email-prompt--hidden');
        setTimeout(function () { el.remove(); }, 250);
    }

    function dismiss() {
        try {
            fetch('/auth/dismiss-email-prompt', {
                method: 'POST',
                headers: { 'X-Requested-With': 'fetch' },
                credentials: 'same-origin'
            });
        } catch (_) { /* best-effort */ }
        hide();
    }

    el.querySelectorAll('[data-action="dismiss"]').forEach(function (b) {
        b.addEventListener('click', dismiss);
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (input.value || '').trim();
        if (!email) return;
        setStatus('Saving…', true);
        fetch('/auth/save-email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'fetch'
            },
            credentials: 'same-origin',
            body: JSON.stringify({ email: email })
        })
            .then(function (r) { return r.json().catch(function () { return { ok: r.ok }; }); })
            .then(function (data) {
                if (data && data.ok) {
                    setStatus('Thanks! You\'re all set.', true);
                    setTimeout(hide, 1200);
                } else {
                    setStatus((data && data.error) || 'Could not save email. Please try again.', false);
                }
            })
            .catch(function () {
                setStatus('Network error. Please try again.', false);
            });
    });
})();
