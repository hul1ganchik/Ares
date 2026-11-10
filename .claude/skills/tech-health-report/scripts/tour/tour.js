/* Presenter tour: a first-run style walk-through for live demos.
   Hidden until the presenter presses T (or calls PresenterTour.open()). Spotlights one area at a time with a short
   talking point, step chips to jump, Back/Next, and optional auto-advance. Page content is never changed.
   Keys while open: Right/Space = next, Left = back, A = auto on/off, L = side column on/off, Esc or T = close.
   Side column (opt-in with rail: true; used on windows 1100 px or wider): the page moves to the left margin and the card and dock sit in a
   column on the right, so they never cover the page. Only margins change; the page's content does not.
   Usage: PresenterTour.init([{label, sel, title, say, points?: [..], note?, before?: async () => {}}], {autoSeconds: 14, rail: true, content: ".wrap"}) */
(function () {
  "use strict";
  const css = `
#ptour-spot{position:fixed;z-index:2147483600;border-radius:10px;pointer-events:none;transition:all .45s cubic-bezier(.22,.8,.3,1);
  box-shadow:0 0 0 4px rgba(43,95,171,.9),0 0 0 9999px rgba(15,20,30,.55)}
#ptour-card{position:fixed;z-index:2147483602;width:340px;max-width:calc(100vw - 32px);background:#fff;color:#1b2230;border-radius:12px;
  box-shadow:0 12px 40px rgba(0,0,0,.35);padding:16px 18px 14px;font:15px/1.45 "IBM Plex Sans","Inter Tight","Segoe UI",system-ui,sans-serif;
  transition:top .45s cubic-bezier(.22,.8,.3,1),left .45s cubic-bezier(.22,.8,.3,1),opacity .25s}
#ptour-card .k{font:600 11px/1 "IBM Plex Mono",Consolas,monospace;letter-spacing:.08em;color:#2b5fab;text-transform:uppercase}
#ptour-card h4{margin:6px 0 6px;font-size:17px;font-weight:600}
#ptour-card p{margin:0;color:#3d4757}
#ptour-card .note{margin:8px 0 0;font-size:12px;line-height:1.35;color:#7a8494}
#ptour-card ul{margin:8px 0 0;padding-left:18px;color:#3d4757;display:grid;gap:5px;font-size:14px;line-height:1.4}
#ptour-card .bar{height:3px;background:#e7eef9;border-radius:3px;margin-top:12px;overflow:hidden}
#ptour-card .bar i{display:block;height:100%;width:0;background:#2b5fab}
#ptour-card .row{display:flex;gap:8px;margin-top:12px;align-items:center}
#ptour-card button,#ptour-dock button{font:600 13px "IBM Plex Sans","Segoe UI",sans-serif;border-radius:7px;cursor:pointer;padding:6px 12px;border:1px solid #c9d3e0;background:#fff;color:#1b2230}
#ptour-card button.pri{background:#2b5fab;border-color:#2b5fab;color:#fff}
#ptour-card .sp{flex:1}
#ptour-dock{position:fixed;z-index:2147483603;left:50%;bottom:14px;transform:translateX(-50%);display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:center;
  max-width:calc(100vw - 24px);background:rgba(27,36,48,.92);padding:8px 10px;border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.3)}
#ptour-dock button{background:transparent;color:#e4e8ef;border-color:rgba(255,255,255,.22);padding:5px 10px}
#ptour-dock button.on{background:#e4e8ef;color:#1b2230}
#ptour-dock .lbl{font:600 11px "IBM Plex Mono",Consolas,monospace;color:#9aa4b5;letter-spacing:.08em;margin:0 4px}
html.ptour-rail body{padding-right:380px!important;box-sizing:border-box}
html.ptour-rail .ptour-content{margin-left:8px!important;margin-right:auto!important}
html.ptour-rail #ptour-dock{left:auto;right:18px;transform:none;width:340px;max-width:340px;justify-content:flex-start}
@media (prefers-reduced-motion:reduce){#ptour-spot,#ptour-card{transition:none}}`;
  let STEPS = [], OPT = { autoSeconds: 14, rail: false, content: ".wrap", railMin: 1100 }, i = -1, open = false, auto = false, timer = null, t0 = 0, raf = 0, els = null;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let railPref = true;
  try { railPref = localStorage.getItem("ptour-rail") !== "off"; } catch (e) { /* storage blocked: default on */ }
  const rail = () => open && OPT.rail && railPref && innerWidth >= OPT.railMin;
  function layout() {
    const c = OPT.content && document.querySelector(OPT.content); if (c) c.classList.add("ptour-content");
    document.documentElement.classList.toggle("ptour-rail", rail());
  }
  function build() {
    if (els) return;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
    const spot = document.createElement("div"); spot.id = "ptour-spot";
    const card = document.createElement("div"); card.id = "ptour-card"; card.setAttribute("role", "dialog"); card.setAttribute("aria-live", "polite");
    const dock = document.createElement("div"); dock.id = "ptour-dock";
    document.body.append(spot, card, dock); els = { spot, card, dock };
    window.addEventListener("resize", () => { layout(); place(); }); window.addEventListener("scroll", place, { passive: true });
  }
  function dockRender() {
    const d = els.dock; d.replaceChildren();
    const lbl = document.createElement("span"); lbl.className = "lbl"; lbl.textContent = "TOUR"; d.appendChild(lbl);
    STEPS.forEach((s, k) => { const b = document.createElement("button"); b.textContent = (k + 1) + " " + s.label; if (k === i) b.className = "on"; b.onclick = () => go(k); d.appendChild(b); });
    const a = document.createElement("button"); a.textContent = auto ? "Auto: on" : "Auto: off"; if (auto) a.className = "on"; a.onclick = toggleAuto; d.appendChild(a);
    const x = document.createElement("button"); x.textContent = "Close"; x.onclick = close; d.appendChild(x);
  }
  function target() { const s = STEPS[i]; return s && s.sel ? document.querySelector(s.sel) : null; }
  function place() {
    if (!open || !els) return;
    const el = target(), pad = 10, vw = innerWidth, vh = innerHeight, card = els.card;
    if (!el) { Object.assign(els.spot.style, { left: vw / 2 + "px", top: vh / 2 + "px", width: "0px", height: "0px" }); card.style.left = (vw - card.offsetWidth) / 2 + "px"; card.style.top = vh * 0.3 + "px"; return; }
    const r = el.getBoundingClientRect();
    const top = Math.max(6, r.top - pad), bottom = Math.min(vh - 6, r.bottom + pad);
    Object.assign(els.spot.style, { left: r.left - pad + "px", top: top + "px", width: r.width + 2 * pad + "px", height: Math.max(20, bottom - top) + "px" });
    const cw = card.offsetWidth, ch = card.offsetHeight, gap = 18;
    let x, y;
    if (rail()) { x = vw - cw - 18; y = Math.min(Math.max(12, r.top), vh - ch - els.dock.offsetHeight - 30); }
    else if (r.right + gap + cw < vw - 12) { x = r.right + gap; y = Math.min(Math.max(12, r.top), vh - ch - 80); }
    else if (r.left - gap - cw > 12) { x = r.left - gap - cw; y = Math.min(Math.max(12, r.top), vh - ch - 80); }
    else { x = Math.min(Math.max(12, r.left), vw - cw - 12); y = 12; }   // wide target: card on top; go() scrolls the target to sit below it
    card.style.left = x + "px"; card.style.top = y + "px";
  }
  function wide(el) { if (rail()) return false; const r = el.getBoundingClientRect(), cw = els.card.offsetWidth || 340; return !(r.right + 18 + cw < innerWidth - 12 || r.left - 18 - cw > 12); }
  function cardRender() {
    const s = STEPS[i], c = els.card; c.replaceChildren();
    const k = document.createElement("div"); k.className = "k"; k.textContent = `Step ${i + 1} of ${STEPS.length}`;
    const h = document.createElement("h4"); h.textContent = s.title;
    const p = document.createElement("p"); p.textContent = s.say;
    const pts = document.createElement("ul"); (s.points || []).forEach(t => { const li = document.createElement("li"); li.textContent = t; pts.appendChild(li); });
    const bar = document.createElement("div"); bar.className = "bar"; bar.appendChild(document.createElement("i"));
    const row = document.createElement("div"); row.className = "row";
    const back = document.createElement("button"); back.textContent = "Back"; back.disabled = i === 0; back.onclick = () => go(i - 1);
    const sp = document.createElement("span"); sp.className = "sp";
    const next = document.createElement("button"); next.className = "pri"; next.textContent = i === STEPS.length - 1 ? "Finish" : "Next"; next.onclick = () => (i === STEPS.length - 1 ? close() : go(i + 1));
    row.append(back, sp, next); c.append(k, h, p); if (pts.children.length) c.append(pts);
    if (s.note) { const nt = document.createElement("p"); nt.className = "note"; nt.textContent = s.note; c.append(nt); }
    c.append(bar, row);
  }
  function tick() {
    if (!auto || !open) return;
    const f = Math.min(1, (performance.now() - t0) / (OPT.autoSeconds * 1000)), bar = els.card.querySelector(".bar i");
    if (bar) bar.style.width = f * 100 + "%";
    if (f >= 1) { i < STEPS.length - 1 ? go(i + 1) : toggleAuto(); return; }
    raf = requestAnimationFrame(tick);
  }
  async function go(k) {
    if (k < 0 || k >= STEPS.length) return;
    i = k; cancelAnimationFrame(raf);
    const s = STEPS[i];
    try { if (s.before) await s.before(); } catch (e) { /* the page keeps working even if a step's setup fails */ }
    await sleep(60);
    cardRender(); dockRender();
    const el = target();
    if (el) {
      if (wide(el)) { const want = els.card.offsetHeight + 40; scrollBy({ top: el.getBoundingClientRect().top - want, behavior: "smooth" }); }
      else el.scrollIntoView({ behavior: "smooth", block: el.offsetHeight > innerHeight * 0.7 ? "start" : "center" });
    }
    for (let n = 0; n < 12; n++) { place(); await sleep(60); }
    t0 = performance.now(); if (auto) raf = requestAnimationFrame(tick);
  }
  function toggleAuto() { auto = !auto; dockRender(); t0 = performance.now(); cancelAnimationFrame(raf); const b = els.card.querySelector(".bar i"); if (b) b.style.width = "0"; if (auto) raf = requestAnimationFrame(tick); }
  function openTour(k) { build(); open = true; layout(); els.spot.style.display = els.card.style.display = els.dock.style.display = ""; go(k || 0); }
  function close() { open = false; auto = false; layout(); cancelAnimationFrame(raf); if (els) els.spot.style.display = els.card.style.display = els.dock.style.display = "none"; }
  document.addEventListener("keydown", e => {
    if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    const key = e.key.toLowerCase();
    if (key === "t" && !e.ctrlKey && !e.metaKey && !e.altKey) { open ? close() : openTour(0); e.preventDefault(); return; }
    if (!open) return;
    if (key === "arrowright" || key === " ") { i < STEPS.length - 1 ? go(i + 1) : close(); e.preventDefault(); }
    else if (key === "arrowleft") { go(i - 1); e.preventDefault(); }
    else if (key === "a") toggleAuto();
    else if (key === "l" && OPT.rail) { railPref = !railPref; try { localStorage.setItem("ptour-rail", railPref ? "on" : "off"); } catch (e) { /* not saved */ } layout(); go(i); }
    else if (key === "escape") close();
  });
  window.PresenterTour = { init(steps, opt) { STEPS = steps || []; Object.assign(OPT, opt || {}); }, open: openTour, close };
})();
