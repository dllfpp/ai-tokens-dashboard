/* Motion with GSAP: cards enter, big figures count up, bars grow, sections reveal once.
   Content is visible without this file; under reduced motion nothing moves. The page reloads
   every 60 s, so a path animates once per 10 minutes. */
(function () {
  if (!window.gsap) return;
  var key = "motion:" + location.pathname, now = Date.now();
  try {
    if (now - (+sessionStorage.getItem(key) || 0) < 600000) return;
    sessionStorage.setItem(key, now);
  } catch (e) {}
  if (window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
  var $ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", function () {
    var fold = window.innerHeight;
    var above = function (el) { return el.getBoundingClientRect().top < fold; };

    // header and the first screen of cards
    var first = $(".top, .hero-s, .pebbles > li, .tray, .split > .slab").filter(above).slice(0, 8);
    gsap.from(first, { y: 12, opacity: 0, duration: 0.45, ease: "power2.out", stagger: 0.06, clearProps: "transform,opacity" });

    // big figures count up to the exact text shown, which is restored at the end
    $(".pebble strong").forEach(function (el) {
      var txt = el.textContent, m = txt.match(/^([^\d]*)([\d.,]+)(.*)$/);
      if (!m) return;
      var n = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, o = { v: 0 };
      if (!isFinite(n)) return;
      gsap.to(o, { v: n, duration: 0.8, ease: "power2.out", delay: 0.1,
        onUpdate: function () { el.textContent = m[1] + o.v.toFixed(dec) + m[3]; },
        onComplete: function () { el.textContent = txt; } });
    });

    // bars: chart columns grow from the floor, gauges from the left
    gsap.from(".chart .bar", { scaleY: 0, transformOrigin: "50% 100%", duration: 0.5, ease: "power2.out", stagger: { amount: 0.3 } });
    $(".fill > span").forEach(function (el) {
      gsap.from(el, { scaleX: 0, transformOrigin: "0% 50%", duration: 0.55, ease: "power2.out",
        scrollTrigger: above(el) ? null : { trigger: el, start: "top 92%", once: true } });
    });
    // plan limit lines draw left to right
    gsap.fromTo(".lim-chart .actual", { clipPath: "inset(0 100% 0 0)" },
      { clipPath: "inset(0 0% 0 0)", duration: 0.8, ease: "power2.out", delay: 0.2, clearProps: "clipPath" });

    // sections below the fold reveal once
    if (window.ScrollTrigger) {
      $(".tray, .split > .slab, .pebbles > li").filter(function (el) { return !above(el); }).forEach(function (el) {
        gsap.from(el, { y: 12, opacity: 0, duration: 0.45, ease: "power2.out", clearProps: "transform,opacity",
          scrollTrigger: { trigger: el, start: "top 90%", once: true } });
      });
    }
  });
})();
