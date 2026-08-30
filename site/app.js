(() => {
  const APP_VERSION = "2026-08-30.2"; // bump on every site/ change — shown at list bottom so phones can confirm which build they run
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const FONT_SIZES = [18, 22, 26, 30];
  const RATES = [1.0, 1.2, 1.5, 2.0];
  const state = { index: [], current: null, sentences: [], activeIdx: -1, userScrollUntil: 0, rateIdx: 0, retryAudio: false };

  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const fmt = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let toastTimer = 0;
  const toast = (msg) => { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), 3000); };

  // ---- font size
  let fontIdx = ls.get("fontIdx", 1);
  const applyFont = () => { document.documentElement.style.setProperty("--font", FONT_SIZES[fontIdx] + "px"); ls.set("fontIdx", fontIdx); };
  $("font-up").onclick = () => { fontIdx = Math.min(FONT_SIZES.length - 1, fontIdx + 1); applyFont(); };
  $("font-down").onclick = () => { fontIdx = Math.max(0, fontIdx - 1); applyFont(); };
  applyFont();

  // ---- list view
  async function loadIndex() {
    const list = $("list");
    list.innerHTML = "<p style='padding:20px;color:var(--muted)'>불러오는 중…</p>";
    try {
      const r = await fetch("./index.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      state.index = await r.json();
      renderList();
    } catch (e) {
      list.innerHTML = "<div class='card'><h2>불러오기 실패</h2><button id='retry' class='icon' style='border-color:var(--muted)'>다시 시도</button></div>";
      $("retry").onclick = loadIndex;
    }
  }
  function renderList() {
    const list = $("list");
    list.innerHTML = "";
    if (!state.index.length) { list.innerHTML = "<p style='padding:20px;color:var(--muted)'>아직 글이 없습니다.</p>"; return; }
    for (const e of state.index) {
      const pos = ls.get("pos:" + e.id, 0);
      const done = ls.get("done:" + e.id, false);
      const pct = done ? 100 : Math.min(100, Math.round(100 * pos / (e.duration || 1)));
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<h2>${escapeHtml(e.title)}</h2>
        <div class="meta"><span>${e.published.slice(0, 10)}</span><span>${Math.max(1, Math.round(e.duration / 60))}분</span>${done ? '<span class="done">✓ 들음</span>' : ""}</div>
        <div class="progress"><div style="width:${pct}%"></div></div>`;
      card.onclick = () => openPost(e.id);
      list.appendChild(card);
    }
    const v = document.createElement("p");
    v.style.cssText = "text-align:center;color:var(--muted);font-size:12px;padding:12px 0 24px";
    v.textContent = "버전 " + APP_VERSION;
    list.appendChild(v);
  }

  // ---- player view
  const metaCache = new Map();
  async function getMeta(id) {
    if (metaCache.has(id)) return metaCache.get(id);
    const r = await fetch(`./posts/${id}.json`);
    if (!r.ok) throw new Error(r.status);
    const meta = await r.json();
    metaCache.set(id, meta);
    return meta;
  }
  function prefetchNext() {
    const n = neighbor(-1);
    if (n && !metaCache.has(n.id)) getMeta(n.id).catch(() => {});
  }
  function renderCaptions() {
    const cap = $("captions");
    cap.innerHTML = "";
    state.sentences.forEach((s) => {
      const p = document.createElement("p");
      p.textContent = s.text;
      p.onclick = () => { audio.currentTime = s.start; audio.play().catch(() => {}); };
      cap.appendChild(p);
    });
  }
  async function loadCaptions(entry) {
    try {
      const meta = await getMeta(entry.id);
      if (state.current !== entry) return;
      state.sentences = meta.sentences;
      state.activeIdx = -1;
      renderCaptions();
      updateCaption();
    } catch (e) { if (state.current === entry && document.visibilityState === "visible") toast("자막을 불러오지 못했습니다"); }
  }
  function openPost(id, autoplay = false) {
    const entry = state.index.find((e) => e.id === id);
    if (!entry) return;
    if (state.current) savePos();
    state.current = entry; state.sentences = []; state.activeIdx = -1;

    history.replaceState(null, "", "#" + id);
    $("title").textContent = entry.title;
    $("back").classList.remove("hidden");
    $("list").classList.add("hidden");
    $("player").classList.remove("hidden");
    $("captions").innerHTML = "";
    window.scrollTo(0, 0);
    $("cur").textContent = "0:00";
    $("seek").value = 0;
    $("dur").textContent = fmt(entry.duration);

    // audio starts first; captions load async and must never block playback
    // (screen off: OS can kill fetches, but the media element keeps playing)
    audio.src = `./posts/${id}.mp3`;
    audio.playbackRate = RATES[state.rateIdx];
    const pos = ls.get("pos:" + id, 0);
    audio.addEventListener("loadedmetadata", () => { if (pos > 0 && pos < audio.duration - 5) audio.currentTime = pos; updateCaption(); }, { once: true });
    setMediaSession(entry);
    if (autoplay) audio.play().catch(() => {});
    loadCaptions(entry);
    prefetchNext();
  }
  function closePost() {
    savePos();
    audio.pause();
    history.replaceState(null, "", location.pathname);
    $("title").textContent = "메르의 블로그";
    $("back").classList.add("hidden");
    $("player").classList.add("hidden");
    $("list").classList.remove("hidden");
    renderList();
  }
  $("back").onclick = closePost;

  function savePos() {
    if (!state.current || audio.error) return; // a failed element reports currentTime 0 — keep the last good pos
    ls.set("pos:" + state.current.id, audio.currentTime);
  }
  function neighbor(delta) {
    if (!state.current) return undefined;
    const i = state.index.findIndex((e) => e.id === state.current.id);
    return state.index[i + delta];
  }

  // ---- caption sync
  function findActive(t) {
    const s = state.sentences; let lo = 0, hi = s.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (s[mid].start <= t + 0.05) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  }
  function updateCaption() {
    const idx = findActive(audio.currentTime);
    if (idx === state.activeIdx) return;
    const ps = $("captions").children;
    for (let i = 0; i < ps.length; i++) { ps[i].classList.toggle("past", i < idx); ps[i].classList.toggle("active", i === idx); }
    state.activeIdx = idx;
    if (idx >= 0 && Date.now() > state.userScrollUntil) ps[idx].scrollIntoView({ block: "center", behavior: "smooth" });
  }
  let lastSave = 0;
  audio.addEventListener("timeupdate", () => {
    updateCaption();
    $("cur").textContent = fmt(audio.currentTime);
    if (audio.duration) $("seek").value = Math.round(1000 * audio.currentTime / audio.duration);
    if (Date.now() - lastSave > 5000) { savePos(); lastSave = Date.now(); }
  });
  audio.addEventListener("play", () => { $("play").textContent = "⏸"; });
  audio.addEventListener("pause", () => { $("play").textContent = "▶"; savePos(); });
  audio.addEventListener("ended", () => {
    ls.set("done:" + state.current.id, true); ls.set("pos:" + state.current.id, 0);
    const next = neighbor(-1); // index is newest-first: -1 = chronologically next (newer)
    if (next) openPost(next.id, true); else closePost();
  });
  audio.addEventListener("error", () => {
    if (!state.current || !audio.error) return;
    if (document.visibilityState === "visible") toast("오디오를 불러오지 못했습니다");
    else state.retryAudio = true; // load died while screen was off — retry silently on return
  });
  ["wheel", "touchmove"].forEach((ev) => window.addEventListener(ev, () => { state.userScrollUntil = Date.now() + 5000; }, { passive: true }));

  // ---- controls
  const seekBy = (d) => { audio.currentTime = Math.min(audio.duration || 0, Math.max(0, audio.currentTime + d)); };
  $("play").onclick = () => (audio.paused ? audio.play().catch(() => {}) : audio.pause());
  $("back15").onclick = () => seekBy(-15);
  $("fwd15").onclick = () => seekBy(15);
  $("prev").onclick = () => { const p = neighbor(1); if (p) openPost(p.id, !audio.paused); };
  const applyRate = () => { audio.playbackRate = RATES[state.rateIdx]; $("rate").textContent = RATES[state.rateIdx].toFixed(1) + "×"; };
  $("rate").onclick = () => { state.rateIdx = (state.rateIdx + 1) % RATES.length; ls.set("rateIdx", state.rateIdx); applyRate(); };
  state.rateIdx = ls.get("rateIdx", 0); applyRate();
  $("seek").oninput = (e) => { if (audio.duration) audio.currentTime = audio.duration * e.target.value / 1000; };

  // ---- keep screen on while playing (like video apps)
  let wakeLock = null;
  async function acquireWake() {
    if (!("wakeLock" in navigator) || wakeLock) return;
    try { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.addEventListener("release", () => { wakeLock = null; }); } catch {}
  }
  function releaseWake() { if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; } }
  audio.addEventListener("play", acquireWake);
  audio.addEventListener("pause", releaseWake);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!audio.paused) acquireWake(); // OS drops the lock when the tab hides; re-grab on return
    if (state.current && !state.sentences.length) loadCaptions(state.current); // captions fetch may have died while hidden
    if (state.retryAudio && state.current) { state.retryAudio = false; openPost(state.current.id, true); }
  });

  function setMediaSession(entry) {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({ title: entry.title, artist: "메르의 블로그", artwork: [{ src: "./icon.svg", sizes: "any", type: "image/svg+xml" }] });
    const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch {} };
    h("play", () => audio.play()); h("pause", () => audio.pause());
    h("seekbackward", () => seekBy(-15)); h("seekforward", () => seekBy(15));
    h("nexttrack", () => { const n = neighbor(-1); if (n) openPost(n.id, true); });
    h("previoustrack", () => $("prev").onclick());
    h("seekto", (d) => { if (d.seekTime != null) audio.currentTime = d.seekTime; });
  }

  // ---- password gate (client-side only: keeps strangers out, not a real secret)
  const PW_HASH = 2576725674;
  const fnv = (str) => { let h = 2166136261; for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h; };
  function boot() {
    $("gate").classList.add("hidden");
    loadIndex().then(() => { const id = location.hash.slice(1); if (id) openPost(id); });
  }
  if (ls.get("auth", 0) === PW_HASH) boot();
  else {
    $("gate").classList.remove("hidden");
    $("gate-form").onsubmit = (e) => {
      e.preventDefault();
      if (fnv($("gate-pw").value.trim()) === PW_HASH) { ls.set("auth", PW_HASH); boot(); }
      else { $("gate-err").classList.remove("hidden"); $("gate-pw").value = ""; $("gate-pw").focus(); }
    };
  }

  // ---- boot
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js").catch(() => {});
  window.addEventListener("pagehide", savePos);
})();
