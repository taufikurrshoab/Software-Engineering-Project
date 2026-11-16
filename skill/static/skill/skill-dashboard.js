/*
 * Skill dashboard accordions (skill/static/skill/skill-dashboard.js)
 * Loaded by skill/home.html next to skill-home.js. Vanilla JS, no libraries.
 *
 *  - turns every [data-skd-acc] into an independent accordion (any number can be open)
 *  - default state comes from data-open="true|false" on the section
 *  - ArrowUp / ArrowDown / Home / End move focus between accordion headers
 *  - after "Refresh AI suggestions" (POST then redirect) the suggestions section
 *    is reopened, so the person sees the new result
 *
 * Without this file the sections simply stay open (the CSS only collapses them
 * once the "skd-js" class is present).
 */
(function () {
    "use strict";

    var accs = Array.prototype.slice.call(document.querySelectorAll("[data-skd-acc]"));
    if (!accs.length) return;

    var root = document.documentElement;
    root.classList.add("skd-js");   // (re)apply in case the inline fallback already removed it
    window.__skdReady = true;

    var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    var FLAG = "skdReopen";

    function parts(acc) {
        return { btn: acc.querySelector(".skd-acc__trigger"), panel: acc.querySelector(".skd-acc__panel") };
    }

    function setOpen(acc, open) {
        var p = parts(acc);
        if (!p.btn || !p.panel) return;
        acc.classList.toggle("is-open", open);
        p.btn.setAttribute("aria-expanded", open ? "true" : "false");
        // Collapsed content must not be reachable by keyboard / screen readers.
        // visibility:hidden in CSS handles this; inert is an extra guard where supported.
        if ("inert" in p.panel) p.panel.inert = !open;
    }

    // initial state (no transition: .is-ready is added on the next frames)
    accs.forEach(function (acc) {
        setOpen(acc, acc.getAttribute("data-open") === "true");
    });

    var reopenId = null;
    try {
        reopenId = sessionStorage.getItem(FLAG);
        if (reopenId) sessionStorage.removeItem(FLAG);
    } catch (e) { /* storage unavailable: ignore */ }

    var reopened = reopenId ? document.getElementById(reopenId) : null;
    if (reopened && reopened.hasAttribute("data-skd-acc")) setOpen(reopened, true);

    requestAnimationFrame(function () {
        requestAnimationFrame(function () {
            accs.forEach(function (acc) { acc.classList.add("is-ready"); });
            if (reopened && reopened.hasAttribute("data-skd-acc")) {
                reopened.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
            }
        });
    });

    accs.forEach(function (acc) {
        var p = parts(acc);
        if (!p.btn) return;
        p.btn.addEventListener("click", function () {
            setOpen(acc, !acc.classList.contains("is-open"));
        });
    });

    // keyboard: move between headers
    var triggers = accs.map(function (a) { return parts(a).btn; }).filter(Boolean);
    triggers.forEach(function (btn, i) {
        btn.addEventListener("keydown", function (e) {
            var next = null;
            if (e.key === "ArrowDown") next = triggers[(i + 1) % triggers.length];
            else if (e.key === "ArrowUp") next = triggers[(i - 1 + triggers.length) % triggers.length];
            else if (e.key === "Home") next = triggers[0];
            else if (e.key === "End") next = triggers[triggers.length - 1];
            if (next) { e.preventDefault(); next.focus(); }
        });
    });

    // remember to reopen the suggestions after the refresh redirect
    var refresh = document.querySelector("[data-skd-refresh]");
    if (refresh) {
        refresh.addEventListener("submit", function () {
            var acc = refresh.closest("[data-skd-acc]");
            try { if (acc && acc.id) sessionStorage.setItem(FLAG, acc.id); } catch (e) { /* ignore */ }
        });
    }
})();
