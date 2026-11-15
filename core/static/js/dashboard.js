/*
 * ThinkSphere dashboard (core/static/js/dashboard.js)
 * Loaded only by core/templates/core/dashboard.html. Vanilla JS, no libraries.
 *
 *  - "Today" card: greeting, date, time and day-progress dial, all read from
 *    the visitor's own device clock (real values, nothing invented)
 *  - scroll reveal for below-the-fold items (IntersectionObserver)
 *  - count-up for numbers marked data-td-count
 *  - subtle 3D tilt + pointer glow on cards (mouse devices only)
 *
 * Progressive enhancement: the page is complete without this file, and the
 * motion parts do not run when the visitor prefers reduced motion.
 */
(function () {
    "use strict";

    var root = document.querySelector(".platform-dashboard");
    if (!root) return;


    /* ---------- Today card (not motion, so it always runs) ---------- */
    (function () {
        var greet = root.querySelector("[data-td-greet]");
        var timeEl = root.querySelector("[data-td-time]");
        var dateEl = root.querySelector("[data-td-date]");
        var dial = root.querySelector("[data-td-dial]");
        var pctEl = root.querySelector("[data-td-dial-pct]");
        if (!timeEl && !dial) return;

        var CIRC = 326.73; // 2 * PI * r(52), matches the SVG dasharray

        function pad(n) { return n < 10 ? "0" + n : String(n); }

        function paint(first) {
            var now = new Date();
            var h = now.getHours(), m = now.getMinutes();

            if (greet) {
                var g = h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : h < 21 ? "Good evening" : "Good night";
                greet.textContent = g;
            }
            if (timeEl) timeEl.textContent = pad(h) + ":" + pad(m);
            if (dateEl && first) {
                try {
                    dateEl.textContent = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
                } catch (e) { /* keep the server-rendered date */ }
            }
            if (dial) {
                var pct = Math.round(((h * 60 + m) / 1440) * 100);
                dial.hidden = false;
                if (pctEl) pctEl.textContent = String(pct);
                // let the browser paint the empty dial first so the fill animates in
                requestAnimationFrame(function () {
                    dial.style.setProperty("--td-dial-off", (CIRC * (1 - pct / 100)).toFixed(2));
                });
            }
        }

        // this-week strip, Monday first
        var week = root.querySelector("[data-td-week]");
        if (week) {
            var today = new Date();
            var monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7));
            var names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
            for (var d = 0; d < 7; d++) {
                var day = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + d);
                var li = document.createElement("li");
                var label = document.createElement("span");
                var num = document.createElement("b");
                label.textContent = names[d];
                num.textContent = String(day.getDate());
                li.appendChild(label);
                li.appendChild(num);
                if (day.getDate() === today.getDate() && day.getMonth() === today.getMonth()) {
                    li.className = "is-today";
                    li.setAttribute("aria-current", "date");
                }
                week.appendChild(li);
            }
            week.hidden = false;
        }

        paint(true);
        setInterval(function () { paint(false); }, 20000);
    })();


    /* ---------- everything below is motion ---------- */
    var mq = window.matchMedia ? window.matchMedia.bind(window) : null;
    if (mq && mq("(prefers-reduced-motion: reduce)").matches) return;

    var canHover = !!(mq && mq("(hover: hover) and (pointer: fine)").matches);
    var hasIO = "IntersectionObserver" in window;
    var viewport = window.innerHeight || document.documentElement.clientHeight;


    /* ---------- scroll reveal ---------- */
    if (hasIO) {
        var items = root.querySelectorAll("[data-td-reveal]");
        var revealIO = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.remove("td-pending");
                revealIO.unobserve(entry.target);
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

        Array.prototype.forEach.call(items, function (el) {
            if (el.getBoundingClientRect().top < viewport * 0.9) return; // visible: CSS entrance plays
            el.classList.add("td-pending");
            revealIO.observe(el);
        });
    }


    /* ---------- count-up ---------- */
    (function () {
        var nodes = root.querySelectorAll("[data-td-count]");
        if (!nodes.length || !hasIO) return;

        function run(el) {
            var target = parseFloat(el.getAttribute("data-td-count"));
            if (isNaN(target)) return;
            var holder = el.closest(".td-progress");
            var idx = holder ? parseFloat(getComputedStyle(holder).getPropertyValue("--td-i")) || 0 : 0;
            var delay = holder ? 400 + idx * 150 : 300;
            var dur = 1200;
            var start = null;
            function frame(now) {
                if (start === null) start = now;
                var t = Math.min(1, Math.max(0, (now - start - delay) / dur));
                el.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
                if (t < 1) requestAnimationFrame(frame);
            }
            el.textContent = "0";
            requestAnimationFrame(frame);
        }

        var countIO = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                countIO.unobserve(entry.target);
                run(entry.target);
            });
        }, { threshold: 0.6 });
        Array.prototype.forEach.call(nodes, function (n) { countIO.observe(n); });
    })();


    /* ---------- tilt + pointer glow (mouse only) ---------- */
    if (canHover) {
        var frame = 0;
        root.addEventListener("pointermove", function (e) {
            var card = e.target.closest && e.target.closest(".td-spot");
            if (!card || frame) return;
            var x = e.clientX, y = e.clientY;
            frame = requestAnimationFrame(function () {
                frame = 0;
                var r = card.getBoundingClientRect();
                var px = x - r.left, py = y - r.top;
                card.style.setProperty("--mx", px + "px");
                card.style.setProperty("--my", py + "px");
                if (card.classList.contains("td-tilt")) {
                    var max = 3; // degrees, kept small on purpose
                    card.style.setProperty("--ry", (((px / r.width) - 0.5) * 2 * max).toFixed(2) + "deg");
                    card.style.setProperty("--rx", (((py / r.height) - 0.5) * -2 * max).toFixed(2) + "deg");
                }
            });
        }, { passive: true });

        root.addEventListener("pointerout", function (e) {
            var card = e.target.closest && e.target.closest(".td-tilt");
            if (!card || (e.relatedTarget && card.contains(e.relatedTarget))) return;
            card.style.setProperty("--rx", "0deg");
            card.style.setProperty("--ry", "0deg");
        });
    }
})();
