(function () {
    if (window.__ritdAnalyticsTrackerLoaded) return;
    window.__ritdAnalyticsTrackerLoaded = true;

    var endpoint = "/api/analytics/activity";
    var sessionId = "";
    var queue = [];
    var flushTimer = null;
    var heartbeatTimer = null;
    var maxScrollDepth = 0;
    var milestones = { 25: false, 50: false, 75: false, 100: false };

    function makeSessionId() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return window.crypto.randomUUID();
        }
        return "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    }

    sessionId = makeSessionId();

    function nowIso() {
        return new Date().toISOString();
    }

    function pagePath() {
        return window.location.pathname || "/";
    }

    function activeNow() {
        return document.visibilityState === "visible" && document.hasFocus();
    }

    var activeStartMs = Date.now();
    var activeAccumMs = 0;

    function pullActiveSeconds() {
        var now = Date.now();
        if (activeNow()) {
            activeAccumMs += Math.max(0, now - activeStartMs);
        }
        activeStartMs = now;
        var secs = Math.floor(activeAccumMs / 1000);
        activeAccumMs = activeAccumMs % 1000;
        return Math.max(0, secs);
    }

    function queueEvent(eventType, eventName, opts) {
        opts = opts || {};
        queue.push({
            ts: nowIso(),
            session_id: sessionId,
            path: pagePath(),
            event_type: eventType || "interaction",
            event_name: eventName || "event",
            active_seconds: Number.isFinite(opts.activeSeconds) ? Math.max(0, opts.activeSeconds) : 0,
            scroll_depth: Number.isFinite(opts.scrollDepth) ? Math.max(0, Math.min(100, Math.round(opts.scrollDepth))) : undefined,
            details: opts.details && typeof opts.details === "object" ? opts.details : undefined,
        });
        if (queue.length >= 10) {
            flush(false);
        }
    }

    function postBatch(batch, useBeacon) {
        if (!batch.length) return;
        var payload = JSON.stringify({ events: batch });
        if (useBeacon && navigator.sendBeacon) {
            try {
                var blob = new Blob([payload], { type: "application/json" });
                navigator.sendBeacon(endpoint, blob);
                return;
            } catch (err) {
                // fall back to fetch below
            }
        }

        fetch(endpoint, {
            method: "POST",
            credentials: "same-origin",
            keepalive: !!useBeacon,
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: payload,
        }).catch(function () {
            // Best-effort analytics only.
        });
    }

    function flush(useBeacon) {
        if (!queue.length) return;
        var batch = queue.splice(0, queue.length);
        postBatch(batch, !!useBeacon);
    }

    function describeElement(el) {
        if (!el || !el.tagName) return "";
        var tag = el.tagName.toLowerCase();
        var id = el.id ? ("#" + el.id) : "";
        var cls = "";
        if (typeof el.className === "string" && el.className.trim()) {
            cls = "." + el.className.trim().split(/\s+/).slice(0, 2).join(".");
        }
        return (tag + id + cls).slice(0, 120);
    }

    function labelForElement(el) {
        if (!el) return "";
        var txt = (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("title"))) || "";
        if (!txt && "innerText" in el) {
            txt = (el.innerText || "").trim().replace(/\s+/g, " ").slice(0, 80);
        }
        if (!txt && "value" in el) {
            txt = String(el.value || "").trim().slice(0, 80);
        }
        return txt;
    }

    function computeScrollDepth() {
        var doc = document.documentElement;
        var body = document.body;
        var scrollTop = window.scrollY || doc.scrollTop || body.scrollTop || 0;
        var viewport = window.innerHeight || doc.clientHeight || 0;
        var full = Math.max(doc.scrollHeight || 0, body.scrollHeight || 0);
        if (!full || full <= viewport) return 100;
        var pct = ((scrollTop + viewport) / full) * 100;
        return Math.max(0, Math.min(100, pct));
    }

    function handleScroll() {
        maxScrollDepth = Math.max(maxScrollDepth, computeScrollDepth());
        [25, 50, 75, 100].forEach(function (mark) {
            if (!milestones[mark] && maxScrollDepth >= mark) {
                milestones[mark] = true;
                queueEvent("scroll", "scroll_depth_reached", {
                    scrollDepth: mark,
                    details: { depth: mark }
                });
            }
        });
    }

    document.addEventListener("visibilitychange", function () {
        queueEvent("lifecycle", document.visibilityState === "visible" ? "tab_visible" : "tab_hidden", {
            activeSeconds: pullActiveSeconds(),
            scrollDepth: maxScrollDepth,
        });
    });

    window.addEventListener("focus", function () {
        activeStartMs = Date.now();
        queueEvent("lifecycle", "window_focus", {
            scrollDepth: maxScrollDepth,
        });
    });

    window.addEventListener("blur", function () {
        queueEvent("lifecycle", "window_blur", {
            activeSeconds: pullActiveSeconds(),
            scrollDepth: maxScrollDepth,
        });
    });

    document.addEventListener("click", function (ev) {
        var target = ev.target && ev.target.closest
            ? ev.target.closest("a,button,[role='button'],input,select,textarea,summary,label")
            : null;
        if (!target) return;

        var details = {
            target: describeElement(target),
            label: labelForElement(target),
        };
        if (target.tagName && target.tagName.toLowerCase() === "a") {
            details.href = (target.getAttribute("href") || "").slice(0, 180);
            queueEvent("navigation", "link_click", { details: details, scrollDepth: maxScrollDepth });
            return;
        }
        queueEvent("interaction", "click", { details: details, scrollDepth: maxScrollDepth });
    }, true);

    document.addEventListener("change", function (ev) {
        var el = ev.target;
        if (!el || !el.tagName) return;
        var tag = el.tagName.toLowerCase();
        if (tag !== "select" && tag !== "input" && tag !== "textarea") return;
        var type = (el.type || "").toLowerCase();
        var value = "";
        if (type === "checkbox" || type === "radio") value = String(!!el.checked);
        else value = (el.value || "").toString().slice(0, 80);

        queueEvent("form", "field_change", {
            details: {
                target: describeElement(el),
                label: labelForElement(el),
                value: value,
            },
            scrollDepth: maxScrollDepth,
        });
    }, true);

    document.addEventListener("submit", function (ev) {
        var form = ev.target;
        if (!form || !form.tagName) return;
        queueEvent("form", "form_submit", {
            details: {
                target: describeElement(form),
                action: (form.getAttribute("action") || "").slice(0, 180),
            },
            scrollDepth: maxScrollDepth,
        });
    }, true);

    ["play", "pause", "ended"].forEach(function (eventName) {
        document.addEventListener(eventName, function (ev) {
            var el = ev.target;
            if (!el || !el.tagName) return;
            var tag = el.tagName.toLowerCase();
            if (tag !== "video" && tag !== "audio") return;
            var time = Number(el.currentTime || 0);
            var duration = Number(el.duration || 0);
            queueEvent("media", "media_" + eventName, {
                details: {
                    target: describeElement(el),
                    current_time: Number.isFinite(time) ? Math.round(time) : 0,
                    duration: Number.isFinite(duration) ? Math.round(duration) : 0,
                },
                scrollDepth: maxScrollDepth,
            });
        }, true);
    });

    window.addEventListener("scroll", handleScroll, { passive: true });

    flushTimer = window.setInterval(function () {
        flush(false);
    }, 5000);

    heartbeatTimer = window.setInterval(function () {
        var activeSeconds = pullActiveSeconds();
        queueEvent("engagement", "heartbeat", {
            activeSeconds: activeSeconds,
            scrollDepth: maxScrollDepth,
        });
    }, 15000);

    function shutdown() {
        if (flushTimer) {
            clearInterval(flushTimer);
            flushTimer = null;
        }
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
        queueEvent("lifecycle", "page_exit", {
            activeSeconds: pullActiveSeconds(),
            scrollDepth: maxScrollDepth,
        });
        flush(true);
    }

    window.addEventListener("pagehide", shutdown);
    window.addEventListener("beforeunload", shutdown);

    handleScroll();
    queueEvent("lifecycle", "page_enter", {
        scrollDepth: maxScrollDepth,
        details: { title: (document.title || "").slice(0, 120) },
    });
})();
