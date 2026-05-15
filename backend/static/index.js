      const SVG_ICONS = {
        music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
        headphones: '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>',
        list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
        dice: '<rect x="2" y="2" width="20" height="20" rx="2"/><circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none"/><circle cx="16" cy="8" r="1.5" fill="currentColor" stroke="none"/><circle cx="8" cy="16" r="1.5" fill="currentColor" stroke="none"/><circle cx="16" cy="16" r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>',
        sparkles: '<path d="M12 2l-2 7H3l6 4.5L6.5 21 12 16l5.5 5L15 13.5 21 9h-7z"/>',
        download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
        refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
        fastForward: '<polygon points="13 19 22 12 13 5 13 19"/><polygon points="2 19 11 12 2 5 2 19"/>',
        lightbulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
        alertTriangle: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
      };
      function icon(name, sizeClass) {
        const svg = SVG_ICONS[name] || '';
        return '<svg class="icon ' + (sizeClass || '') + '" viewBox="0 0 24 24">' + svg + '</svg>';
      }

      // Global error handler:
      // - Do NOT spam end users with low-signal messages like "Script error. at line 0"
      //   (often caused by cross-origin errors where the browser hides details).
      // - Provide a debug UI only when explicitly enabled.
      const _debugUiErrors = (() => {
        try { return new URLSearchParams(location.search).has("debug"); } catch { return false; }
      })();
      window.onerror = function(msg, url, line, col, error) {
        try {
          const m = String(msg || "");
          const isGenericScriptError = (m === "Script error." || m === "Script error") && (!url || line === 0);
          if (isGenericScriptError) return false;
          if (!_debugUiErrors) return false;

          var el = document.getElementById("js-error-display");
          if (!el) {
            el = document.createElement("div");
            el.id = "js-error-display";
            el.style.cssText = "position:fixed;z-index:99999;top:0;left:0;right:0;padding:16px;background:rgba(239,68,68,0.95);color:white;white-space:pre-wrap;font-family:monospace;font-size:13px;max-height:220px;overflow:auto;box-shadow:0 4px 20px rgba(0,0,0,0.4);";
            if (document.body) document.body.appendChild(el);
          }
          if (el) {
            const where = (url ? (String(url).split("/").slice(-1)[0]) : "") + (line ? (":" + line) : "");
            const stack = (error && error.stack) ? ("\n" + String(error.stack).slice(0, 1200)) : "";
            el.textContent += "JS Error: " + m + (where ? (" @ " + where) : "") + stack + "\n";
          }
        } catch {}
        return false;
      };

      const statusEl = document.getElementById("status");
      const errorEl = document.getElementById("error");
      const jobIdEl = document.getElementById("jobId");
      const player = document.getElementById("player");
      const playerTimeEl = document.getElementById("playerTime");
      const _fmtTime = (s) => { if (!s || !isFinite(s)) return "--:--"; const m = Math.floor(s / 60); return m + ":" + String(Math.floor(s % 60)).padStart(2, "0"); };
      if (player && playerTimeEl) {
        player.addEventListener("loadedmetadata", () => { playerTimeEl.textContent = "0:00 / " + _fmtTime(player.duration); });
        player.addEventListener("timeupdate", () => { playerTimeEl.textContent = _fmtTime(player.currentTime) + " / " + _fmtTime(player.duration); });
      }
      const downloadLink = document.getElementById("downloadLink");
      const refreshBtn = document.getElementById("refreshBtn");
      const extendBtn = document.getElementById("extendBtn");
      const extendGroup = document.getElementById("extendGroup");
      const listEl = document.getElementById("list");
      const list2El = document.getElementById("list2");
      const historyPageSizeEl = document.getElementById("historyPageSize");
      const historyPageSizeEl2 = document.getElementById("historyPageSize2");
      const historyPrevBtn = document.getElementById("historyPrevBtn");
      const historyPrevBtn2 = document.getElementById("historyPrevBtn2");
      const historyNextBtn = document.getElementById("historyNextBtn");
      const historyNextBtn2 = document.getElementById("historyNextBtn2");
      const historyInfoEl = document.getElementById("historyInfo");
      const historyInfoEl2 = document.getElementById("historyInfo2");
      const advancedEl = document.getElementById("advanced");
      const providerFieldsEl = document.getElementById("providerFields");
      const audioUploadSection = document.getElementById("audioUploadSection");
      const srcAudioInput = document.getElementById("srcAudioInput");
      const refAudioInput = document.getElementById("refAudioInput");
      const srcAudioInfo = document.getElementById("srcAudioInfo");
      const refAudioInfo = document.getElementById("refAudioInfo");
      const audioUploadSectionMobile = document.getElementById("audioUploadSectionMobile");
      const srcAudioInputMobile = document.getElementById("srcAudioInputMobile");
      const refAudioInputMobile = document.getElementById("refAudioInputMobile");
      const srcAudioInfoMobile = document.getElementById("srcAudioInfoMobile");
      const refAudioInfoMobile = document.getElementById("refAudioInfoMobile");
      let srcAudioUploadId = null;
      let srcAudioB64 = null;
      let srcAudioFormat = null;
      let refAudioUploadId = null;
      let refAudioB64 = null;
      let refAudioFormat = null;
      const cpEditorEl = document.getElementById("compositionPlanEditor");
      const durationSlider = document.getElementById("duration");
      const durationValue = document.getElementById("durationValue");
      const promptEl = document.getElementById("prompt");
      const lyricsRowEl = document.getElementById("lyricsRow");
      const lyricsEl = document.getElementById("lyrics");
      const lyricsHintEl = document.getElementById("lyricsHint");
      const authPage = document.getElementById("authPage");
      const authErrorEl = document.getElementById("authError");
      const loginPanel = document.getElementById("loginPanel");
      const registerPanel = document.getElementById("registerPanel");
      const showLoginBtn = document.getElementById("showLoginBtn");
      const showRegisterBtn = document.getElementById("showRegisterBtn");
      const quotaInfoEl = document.getElementById("quotaInfo");
      const appLayout = document.getElementById("appLayout");
      const pcLayout = document.getElementById("pcLayout");
      const discoverPage = document.getElementById("discoverPage");
      const communityListEl = document.getElementById("communityList");
      const communityListEl2 = document.getElementById("communityList2");
      const navCreate = document.getElementById("navCreate");
      const navDiscover = document.getElementById("navDiscover");
      const userDropdownBtn = document.getElementById("userDropdownBtn");
      const userDropdownMenu = document.getElementById("userDropdownMenu");
      const mobileTabBar = document.getElementById("mobileTabBar");
      const stickyPlayerBar = document.getElementById("stickyPlayerBar");
      const stickyPlayer = document.getElementById("stickyPlayer");
      const stickyDownloadLink = document.getElementById("stickyDownloadLink");
      const subTabOriginal = document.getElementById("subTabOriginal");
      const subTabRemix = document.getElementById("subTabRemix");
      const accountNameEl = document.getElementById("accountName");
      const adminLink = document.getElementById("adminLink");
      const HISTORY_PAGE_SIZE_KEY = "you2music.historyPageSize.v1";
      let currentJobId = null;
      let currentJobs = [];
      let currentJobSongId = null;
      let currentJobProvider = null;
      let currentMainAudioUrl = null;
      let currentUser = null;
      let authToken = ""; try { authToken = localStorage.getItem("you2music.jwt") || ""; } catch (e) { console.warn("localStorage unavailable:", e); }
      let localMode = false;
      let pollTimer = null;
      let providersMeta = null;
      const DEFAULT_PROVIDER_ID = "acestep";
      let historyOffset = 0;
      let historyLimit = 20;
      let historyTotal = 0;
      let historyJobs = [];
      const liveJobsById = new Map();
      const audioBlobUrlsByUrl = new Map();
      let cpState = { positive_global_styles: [], negative_global_styles: [], sections: [], bpm: null, key: null };
      let draggedSection = null;
      let creationMode = "original";
      let creationSubMode = "simple";
      let currentView = "create";
      let currentMobileTab = "create";

      // Keep this in sync with CSS breakpoints in `index.css`.
      function _isDesktopViewport() { return window.innerWidth >= 1100; }
      function _pickContainer(pcEl, mobileEl) {
        // Prefer viewport-based decision; do not rely on .style.display because we hide panels via CSS classes.
        if (_isDesktopViewport()) return pcEl || mobileEl;
        return mobileEl || pcEl;
      }

      const statusMobileEl = document.getElementById("statusMobile");
      const errorMobileEl = document.getElementById("errorMobile");
      const generateBtnMobile = document.getElementById("generateBtnMobile");
      const promptMobileEl = document.getElementById("promptMobile");
      const durationMobileSlider = document.getElementById("durationMobile");
      const durationMobileValue = document.getElementById("durationValueMobile");
      const providerFieldsMobileEl = document.getElementById("providerFieldsMobile");
      const lyricsMobileEl = document.getElementById("lyricsMobile");
      const vocalsMobileEl = document.getElementById("vocalsMobile");
      const seedMobileEl = document.getElementById("seedMobile");
      const countMobileEl = document.getElementById("countMobile");
      const playerMobile = document.getElementById("playerMobile");
      const downloadLinkMobile = document.getElementById("downloadLinkMobile");
      const jobIdMobileEl = document.getElementById("jobIdMobile");

      function setStatus(msg, kind) {
        statusEl.textContent = msg || "";
        statusEl.className = kind === "ok" ? "status-text success" : (kind === "err" ? "status-text error" : "status-text");
        if (statusMobileEl) { statusMobileEl.textContent = msg || ""; statusMobileEl.className = statusEl.className; }
      }

      function setError(msg) {
        errorEl.textContent = msg || "";
        errorEl.style.display = msg ? "block" : "none";
        if (errorMobileEl) { errorMobileEl.textContent = msg || ""; errorMobileEl.style.display = msg ? "block" : "none"; }
      }

      function setAuthError(msg) {
        authErrorEl.textContent = msg || "";
        authErrorEl.style.display = msg ? "block" : "none";
      }

      function errorMessage(err) {
        return err && err.message ? String(err.message) : String(err || "请求失败");
      }

      function formatApiError(data, fallback) {
        if (!data) return fallback || "请求失败";
        const detail = data.detail !== undefined ? data.detail : (data.error !== undefined ? data.error : data.raw);
        if (Array.isArray(detail)) {
          const lines = detail.map(item => {
            if (!item || typeof item !== "object") return String(item);
            const field = Array.isArray(item.loc) ? item.loc.filter(x => x !== "body").join(".") : "";
            return formatValidationItem(field, item);
          }).filter(Boolean);
          return lines.length ? lines.join("\n") : (fallback || "输入不符合要求");
        }
        if (detail && typeof detail === "object") {
          if (detail.msg || detail.message) return String(detail.msg || detail.message);
          try { return JSON.stringify(detail); } catch { return fallback || "请求失败"; }
        }
        return String(detail || fallback || "请求失败");
      }

      function fieldLabel(field) {
        const labels = { username: "用户名", password: "密码", invite_code: "邀请码", old_password: "当前密码", new_password: "新密码" };
        return labels[field] || field || "输入";
      }

      function formatValidationItem(field, item) {
        const label = fieldLabel(field);
        const type = item.type || "";
        const ctx = item.ctx || {};
        if (type === "missing") return "请填写" + label;
        if (type === "string_too_short") return label + "至少需要 " + (ctx.min_length || 1) + " 个字符";
        if (type === "string_too_long") return label + "不能超过 " + (ctx.max_length || "限制") + " 个字符";
        if (type === "string_pattern_mismatch") return label + "格式不正确";
        if (type === "string_type") return label + "必须是文本";
        return label + ": " + (item.msg || item.message || "输入不符合要求");
      }

      function showAuthMode(mode) {
        const isRegister = mode === "register";
        loginPanel.classList.toggle("hidden", isRegister);
        registerPanel.classList.toggle("hidden", !isRegister);
        showLoginBtn.classList.toggle("active", !isRegister);
        showRegisterBtn.classList.toggle("active", isRegister);
        document.getElementById("authModeText").textContent = isRegister ? "登录" : "注册";
        setAuthError("");
      }

      async function fetchJson(url, opts) {
        const nextOpts = Object.assign({}, opts || {});
        const headers = Object.assign({}, nextOpts.headers || {});
        const urlStr = String(url || "");
        const isAuthRoute = urlStr.startsWith("/api/auth/login") || urlStr.startsWith("/api/auth/register");
        if (!isAuthRoute && authToken && !headers.authorization && !headers.Authorization) {
          headers.Authorization = "Bearer " + authToken;
        }
        nextOpts.headers = headers;
        const res = await fetch(url, nextOpts);
        const text = await res.text();
        let data;
        try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
        if (!res.ok) {
          // 401 handling:
          // - If request carried an Authorization header, treat as token-expired and clear session.
          // - Otherwise, surface backend error detail (e.g. "用户名或密码错误").
          const sentAuth = Boolean(headers.Authorization || headers.authorization);
          if (res.status === 401 && sentAuth) { setSession("", null); stopEventStream(); throw new Error("登录已过期，请重新登录。"); }
          throw new Error(formatApiError(data, text || "HTTP " + res.status));
        }
        return data;
      }

      let eventAbort = null;
      let eventStreamRunning = false;
      let historyRefreshTimer = null;
      // Prevent browsers (notably mobile Safari) from restoring a stale scroll
      // position that makes the first viewport look "empty".
      try { if ("scrollRestoration" in history) history.scrollRestoration = "manual"; } catch {}
      function _forceScrollTop() {
        try { const el = document.activeElement; if (el && typeof el.blur === "function") el.blur(); } catch {}
        try { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); } catch { try { window.scrollTo(0, 0); } catch {} }
        try { document.documentElement.scrollTop = 0; } catch {}
        try { document.body.scrollTop = 0; } catch {}
      }
      try { window.addEventListener("pageshow", () => { _forceScrollTop(); setTimeout(_forceScrollTop, 50); setTimeout(_forceScrollTop, 250); }, { passive: true }); } catch {}
      try { window.addEventListener("load", () => { _forceScrollTop(); setTimeout(_forceScrollTop, 50); }, { passive: true }); } catch {}
      let viewportResizeTimer = null;
      let lastDesktopViewport = _isDesktopViewport();
      function handleViewportResize() {
        const nowDesktop = _isDesktopViewport();
        if (nowDesktop === lastDesktopViewport) return;
        lastDesktopViewport = nowDesktop;
        const loggedIn = localMode || Boolean(currentUser && authToken);
        syncSessionLayout(loggedIn);
        // Move lists into the newly visible container.
        try { renderList(historyJobs || []); } catch {}
        if (currentView === "discover") { loadCommunity().catch(() => {}); }
      }
      try { window.addEventListener("resize", () => { if (viewportResizeTimer) clearTimeout(viewportResizeTimer); viewportResizeTimer = setTimeout(handleViewportResize, 200); }, { passive: true }); } catch {}
      function scheduleHistoryRefresh() {
        if (historyRefreshTimer) return;
        historyRefreshTimer = setTimeout(() => { historyRefreshTimer = null; loadHistoryPage(historyOffset).catch(() => {}); }, 600);
      }
      function stopEventStream() { if (eventAbort) { try { eventAbort.abort(); } catch {} } eventAbort = null; eventStreamRunning = false; }
      function startEventStream() {
        if (localMode) { stopEventStream(); return; }
        if (!authToken) { stopEventStream(); return; }
        if (eventStreamRunning) return;
        eventAbort = new AbortController();
        eventStreamRunning = true;
        runEventStream(authToken, eventAbort.signal).catch(() => { stopEventStream(); setTimeout(() => { if (!localMode && authToken) startEventStream(); }, 1500); });
      }
      function _handleRealtimeEvent(evtType, payload) {
        if (!payload || typeof payload !== "object") return;
        if (evtType === "job_created" || evtType === "job_updated") { scheduleHistoryRefresh(); const jid = payload.job_id; if (jid && Array.isArray(currentJobs) && currentJobs.includes(jid)) { refreshJobs(currentJobs).catch(() => {}); } }
        else if (evtType === "job_progress") { const jid = payload.job_id; const content = payload.content || ""; if (jid && content) { const card = document.querySelector('[data-job-id="' + jid + '"]'); if (card) { let prog = card.querySelector(".job-progress-text"); if (!prog) { prog = document.createElement("p"); prog.className = "job-progress-text"; prog.style.cssText = "margin:6px 0 0;font-size:12px;color:var(--color-text-muted);white-space:pre-wrap;"; const status = card.querySelector(".job-status"); if (status && status.nextSibling) { status.parentNode.insertBefore(prog, status.nextSibling); } else { card.appendChild(prog); } } prog.textContent = content.length > 200 ? content.slice(0, 200) + "..." : content; } } }
      }
      async function runEventStream(token, signal) {
        const res = await fetch("/api/events", { method: "GET", headers: { "Accept": "text/event-stream", "Authorization": "Bearer " + token }, signal });
        if (!res.ok) { const text = await res.text().catch(() => ""); throw new Error(text || "HTTP " + res.status); }
        if (!res.body) return;
        const reader = res.body.getReader(); const decoder = new TextDecoder("utf-8"); let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          while (true) {
            const idx = buf.indexOf("\n\n");
            if (idx < 0) break;
            const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
            let evtType = "message"; let dataStr = "";
            for (const line of chunk.split("\n")) { if (line.startsWith("event:")) evtType = line.slice(6).trim() || "message"; if (line.startsWith("data:")) dataStr += line.slice(5).trim(); }
            if (!dataStr) continue;
            let payload = null; try { payload = JSON.parse(dataStr); } catch { payload = null; }
            _handleRealtimeEvent(evtType, payload);
          }
        }
      }
      async function getAuthenticatedAudioUrl(url) {
        if (!url || !authToken) return url;
        if (audioBlobUrlsByUrl.has(url)) return audioBlobUrlsByUrl.get(url);
        const res = await fetch(url, { headers: { Authorization: "Bearer " + authToken } });
        if (res.status === 401) { setSession("", null); setAuthError("登录已过期，请重新登录。"); stopEventStream(); throw new Error("登录已过期，请重新登录。"); }
        if (!res.ok) { const text = await res.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; } throw new Error(formatApiError(data, text || "HTTP " + res.status)); }
        const blob = await res.blob(); const blobUrl = URL.createObjectURL(blob); audioBlobUrlsByUrl.set(url, blobUrl); return blobUrl;
      }
      function revokeAudioBlobUrls() { for (const url of audioBlobUrlsByUrl.values()) { URL.revokeObjectURL(url); } audioBlobUrlsByUrl.clear(); }
      function cleanupUnusedAudioBlobUrls(activeOriginalUrls) {
        if (!activeOriginalUrls || typeof activeOriginalUrls.has !== "function") return;
        for (const [origUrl, blobUrl] of audioBlobUrlsByUrl.entries()) {
          if (activeOriginalUrls.has(origUrl)) continue;
          try { URL.revokeObjectURL(blobUrl); } catch {}
          audioBlobUrlsByUrl.delete(origUrl);
        }
      }
      function attachAuthenticatedAudio(audioEl, url) {
        try { audioEl.dataset.originalAudioUrl = String(url || ""); } catch {}
        audioEl.removeAttribute("src"); audioEl.load();
        getAuthenticatedAudioUrl(url).then(src => { audioEl.src = src; }).catch(e => { setError(errorMessage(e)); });
      }
      function setMainPlayerAudio(job) {
        if (!job || !job.audio_url) { currentMainAudioUrl = null; player.removeAttribute("src"); player.load(); downloadLink.style.display = "none"; extendGroup.style.display = "none"; if (stickyPlayer) { stickyPlayer.removeAttribute("src"); stickyPlayer.load(); } if (stickyPlayerBar) stickyPlayerBar.classList.remove("playing"); if (stickyDownloadLink) stickyDownloadLink.style.display = "none"; if (playerMobile) { playerMobile.removeAttribute("src"); playerMobile.load(); } if (downloadLinkMobile) downloadLinkMobile.style.display = "none"; return; }
        currentMainAudioUrl = String(job.audio_url || "").trim() || null;
        player.removeAttribute("src"); player.load();
        getAuthenticatedAudioUrl(job.audio_url).then(src => { player.src = src; downloadLink.href = src; downloadLink.setAttribute("download", (job.job_id || "audio") + ".mp3"); downloadLink.style.display = "inline"; extendGroup.style.display = "inline-flex"; if (stickyPlayer) { stickyPlayer.src = src; } if (stickyPlayerBar) stickyPlayerBar.classList.add("playing"); if (stickyDownloadLink) { stickyDownloadLink.href = src; stickyDownloadLink.setAttribute("download", (job.job_id || "audio") + ".mp3"); stickyDownloadLink.style.display = "inline"; } if (playerMobile) { playerMobile.src = src; } if (downloadLinkMobile) { downloadLinkMobile.href = src; downloadLinkMobile.setAttribute("download", (job.job_id || "audio") + ".mp3"); downloadLinkMobile.style.display = "inline"; } if (jobIdMobileEl) jobIdMobileEl.textContent = job.job_id || "-"; }).catch(e => { downloadLink.style.display = "none"; extendGroup.style.display = "none"; setError(errorMessage(e)); });
      }
      function updateQuotaDisplay(user) { const quota = user && user.quota ? user.quota : null; const text = !quota ? "今日配额：-" : "今日配额：" + quota.used + "/" + quota.limit + "，剩余 " + quota.remaining; quotaInfoEl.textContent = text; const qm = document.getElementById("quotaInfoMobile"); if (qm) qm.textContent = text; }

      function showView(view) {
        currentView = view;
        const isPC = _isDesktopViewport();
        if (isPC) {
          pcLayout.classList.toggle("hidden", view === "discover");
          discoverPage.classList.toggle("hidden", view !== "discover");
          navCreate.classList.toggle("active", view === "create");
          navDiscover.classList.toggle("active", view === "discover");
        }
        // Ensure the visible content starts at the top when switching views.
        try { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); } catch { try { window.scrollTo(0, 0); } catch {} }
        if (view === "discover") loadCommunity().catch(e => setError(errorMessage(e)));
        if (!isPC) {
          // Mobile should respect the requested view. Previously this used
          // `currentMobileTab` for non-discover views, which could keep users on
          // the Discover tab after login (because logged-out state sets it).
          if (view === "create") showMobileTab("create");
          else if (view === "discover") showMobileTab("discover");
          else showMobileTab(currentMobileTab);
        }
      }

      function showMobileTab(tab) {
        currentMobileTab = tab;
        if (!mobileTabBar) return;
        // Reset scroll so newly shown panel starts at a sane position.
        try { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); } catch { try { window.scrollTo(0, 0); } catch {} }
        mobileTabBar.querySelectorAll(".tab-item").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
        document.querySelectorAll(".mobile-panel").forEach(p => p.classList.remove("active"));
        const panelMap = { create: "panelCreate", history: "panelHistory", discover: "panelDiscover", profile: "panelProfile" };
        const panel = document.getElementById(panelMap[tab]);
        if (panel) panel.classList.add("active");
        if (tab === "discover") loadCommunity().catch(e => setError(errorMessage(e)));
      }

      function _syncModeDataset() {
        try {
          document.documentElement.dataset.creationMode = creationMode;
          document.documentElement.dataset.creationSub = creationSubMode;
        } catch {}
      }

      function _jobPollIntervalMs() { return eventStreamRunning ? 8000 : 1500; }
      function startJobPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = setInterval(() => refreshJobs(currentJobs), _jobPollIntervalMs()); }

      function setCreationMode(mode) {
        creationMode = mode;
        _syncModeDataset();
        document.querySelectorAll(".mode-tab").forEach(t => t.classList.toggle("active", t.dataset.mode === mode));
        subTabOriginal.classList.toggle("hidden", mode !== "original");
        subTabRemix.classList.toggle("hidden", mode !== "remix");
        document.querySelectorAll("#subTabOriginalMobile").forEach(el => el.classList.toggle("hidden", mode !== "original"));
        document.querySelectorAll("#subTabRemixMobile").forEach(el => el.classList.toggle("hidden", mode !== "remix"));
        if (mode === "original") setCreationSubMode("simple");
        else setCreationSubMode("style-transfer");
      }

      function setCreationSubMode(sub) {
        creationSubMode = sub;
        _syncModeDataset();
        const group = creationMode === "original" ? "#subTabOriginal .sub-tab, #subTabOriginalMobile .sub-tab" : "#subTabRemix .sub-tab, #subTabRemixMobile .sub-tab";
        document.querySelectorAll(group).forEach(t => t.classList.toggle("active", t.dataset.sub === sub));
        if (creationMode === "original") advancedEl.value = sub === "advanced" ? "advanced" : "simple";
        renderProviderFields({ reset: true });
      }

      function _isOriginalSimpleMode() { return creationMode === "original" && creationSubMode === "simple"; }
      function _isOriginalAdvancedMode() { return creationMode === "original" && creationSubMode === "advanced"; }
      function _isRemixMode() { return creationMode === "remix"; }
      function _preferredRemixTaskType() {
        // Map remix sub-modes to ACE-Step task_type defaults.
        if (creationSubMode === "style-transfer") return "cover";
        if (creationSubMode === "section-edit") return "repaint";
        if (creationSubMode === "audio-process") return "extract";
        return "cover";
      }

      function showToast(message, type, duration) {
        type = type || "info"; duration = duration || 3000;
        const container = document.getElementById("toastContainer");
        if (!container) return;
        const toast = document.createElement("div");
        toast.className = "toast toast-" + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() { toast.style.opacity = "0"; toast.style.transform = "translateX(20px)"; setTimeout(function() { toast.remove(); }, 200); }, duration);
      }

      function setSession(token, user) {
        authToken = token || ""; currentUser = user || null;
        try { if (authToken) localStorage.setItem("you2music.jwt", authToken); else localStorage.removeItem("you2music.jwt"); } catch (e) { console.warn("localStorage unavailable:", e); }
        const loggedIn = localMode || Boolean(currentUser && authToken);
        // Mark session resolved so the boot splash (used to avoid auth-page flash) can hide.
        try {
          document.documentElement.classList.add("session-ready");
          if (!loggedIn) document.documentElement.classList.remove("has-token");
        } catch {}
        authPage.classList.toggle("hidden", loggedIn);
        appLayout.classList.toggle("hidden", !loggedIn);
        syncSessionLayout(loggedIn);
        console.log("setSession: loggedIn=", loggedIn, "authPage.hidden=", authPage.classList.contains("hidden"), "appLayout.hidden=", appLayout.classList.contains("hidden"));
        // Some mobile browsers restore/retain scroll positions across view toggles.
        // Force a sane top-of-page baseline when switching auth <-> app.
        try { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); } catch { try { window.scrollTo(0, 0); } catch {} }
        try { document.documentElement.scrollTop = 0; } catch {}
        try { document.body.scrollTop = 0; } catch {}
        if (adminLink) adminLink.style.display = (loggedIn && !localMode && currentUser && currentUser.role === "admin") ? "inline-block" : "none";
        const adminLinkMobile = document.getElementById("adminLinkMobile");
        if (adminLinkMobile) adminLinkMobile.style.display = (loggedIn && !localMode && currentUser && currentUser.role === "admin") ? "block" : "none";
        const accountNameMobile = document.getElementById("accountNameMobile");
        if (loggedIn) {
          if (localMode) { if (accountNameEl) accountNameEl.textContent = "本地模式"; if (accountNameMobile) accountNameMobile.textContent = "本地模式"; updateQuotaDisplay(null); }
          else { if (accountNameEl) accountNameEl.textContent = (currentUser && currentUser.username) ? currentUser.username : "-"; if (accountNameMobile) accountNameMobile.textContent = (currentUser && currentUser.username) ? currentUser.username : "-"; updateQuotaDisplay(currentUser); }
          if (!localMode && currentUser && currentUser.must_change_password) { showForceChangePwd(); }
          else { showView("create"); }
        } else { if (accountNameEl) accountNameEl.textContent = "-"; if (accountNameMobile) accountNameMobile.textContent = "-"; updateQuotaDisplay(null); showView("discover"); }
      }
      function syncSessionLayout(loggedIn) {
        const mobilePanelsEl = document.getElementById("mobilePanels");
        // Enforce visibility via JS too (not only CSS) so that if breakpoints or
        // cached CSS ever drift, mobile won't end up with a huge PC layout above it.
        const isDesktop = _isDesktopViewport();
        if (pcLayout) pcLayout.style.display = (loggedIn && isDesktop) ? "" : "none";
        if (mobilePanelsEl) mobilePanelsEl.style.display = (loggedIn && !isDesktop) ? "" : "none";
        if (mobileTabBar) mobileTabBar.style.display = (loggedIn && !isDesktop) ? "" : "none";
      }
      function showForceChangePwd() { const overlay = document.getElementById("forceChangePwdOverlay"); overlay.classList.add("visible"); document.getElementById("fcpOldPwd").value = ""; document.getElementById("fcpNewPwd").value = ""; document.getElementById("fcpConfirmPwd").value = ""; document.getElementById("fcpError").style.display = "none"; }
      async function submitForceChangePwd() {
        const oldPwd = document.getElementById("fcpOldPwd").value; const newPwd = document.getElementById("fcpNewPwd").value; const confirmPwd = document.getElementById("fcpConfirmPwd").value; const errEl = document.getElementById("fcpError"); errEl.style.display = "none";
        if (!oldPwd || !newPwd) { errEl.textContent = "请填写所有字段"; errEl.style.display = "block"; return; }
        if (newPwd.length < 8) { errEl.textContent = "新密码至少8位"; errEl.style.display = "block"; return; }
        if (newPwd !== confirmPwd) { errEl.textContent = "两次输入的新密码不一致"; errEl.style.display = "block"; return; }
        try { await fetchJson("/api/auth/password", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }) }); document.getElementById("forceChangePwdOverlay").classList.remove("visible"); const me = await fetchJson("/api/auth/me"); currentUser = me.user; showView("create"); }
        catch (e) { errEl.textContent = errorMessage(e); errEl.style.display = "block"; }
      }
      let _editingJobId = null;
      function showEditMetadata(j) {
        _editingJobId = j.job_id;
        const meta = j.metadata || {};
        document.getElementById("metaTitle").value = meta.title || "";
        document.getElementById("metaAuthor").value = meta.author || "";
        document.getElementById("metaAlbum").value = meta.album || "";
        document.getElementById("metaTags").value = (meta.tags || []).join(",");
        document.getElementById("metaDescription").value = meta.description || "";
        document.getElementById("metaError").style.display = "none";
        document.getElementById("editMetadataOverlay").classList.add("visible");
      }
      function hideEditMetadata() {
        document.getElementById("editMetadataOverlay").classList.remove("visible");
        _editingJobId = null;
      }
      function showSongInfo(job) {
        const meta = job.metadata || {};
        const overlay = document.getElementById("songInfoOverlay");
        const body = document.getElementById("songInfoBody");
        const rows = [];
        rows.push(["标题", meta.title || job.prompt || "未命名作品"]);
        if (meta.author) rows.push(["作者", meta.author]);
        if (meta.album) rows.push(["专辑", meta.album]);
        if (meta.tags && meta.tags.length > 0) rows.push(["标签", meta.tags.join("、")]);
        if (meta.description) rows.push(["简介", meta.description]);
        rows.push(["Provider", job.provider || "-"]);
        if (job.duration_sec) rows.push(["时长", Math.round(job.duration_sec) + " 秒"]);
        rows.push(["分享", job.share_permission === "downloadable" ? "可下载" : "仅试听"]);
        const created = job.created_at_ms ? new Date(job.created_at_ms).toLocaleString("zh-CN") : "-";
        rows.push(["创建时间", created]);
        body.innerHTML = "";
        for (const [label, value] of rows) {
          const row = document.createElement("div");
          row.className = "song-info-row";
          const lbl = document.createElement("span");
          lbl.className = "song-info-label";
          lbl.textContent = label + "：";
          const val = document.createElement("span");
          val.className = "song-info-value";
          val.textContent = value;
          row.appendChild(lbl);
          row.appendChild(val);
          body.appendChild(row);
        }
        overlay.classList.add("visible");
      }
      function hideSongInfo() {
        document.getElementById("songInfoOverlay").classList.remove("visible");
      }
      async function saveEditMetadata() {
        if (!_editingJobId) return;
        const errEl = document.getElementById("metaError"); errEl.style.display = "none";
        const title = document.getElementById("metaTitle").value.trim();
        const author = document.getElementById("metaAuthor").value.trim();
        const album = document.getElementById("metaAlbum").value.trim();
        const tagsRaw = document.getElementById("metaTags").value;
        const description = document.getElementById("metaDescription").value.trim();
        const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];
        try {
          await fetchJson("/api/jobs/" + _editingJobId + "/metadata", {
            method: "PATCH",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ title: title || null, author: author || null, album: album || null, tags: tags.length > 0 ? tags : null, description: description || null })
          });
          hideEditMetadata();
          await loadHistoryPage(historyOffset);
          loadCommunity().catch(() => {});
        } catch (e) { errEl.textContent = errorMessage(e); errEl.style.display = "block"; }
      }
      async function detectLocalMode() { try { const res = await fetch("/api/auth/me", { method: "GET" }); return Boolean(res && res.status === 404); } catch { return false; } }
      async function refreshCurrentUser() {
        if (!authToken) { localMode = await detectLocalMode(); if (localMode) { setSession("", { username: "本地模式", role: "user", must_change_password: false, quota: null }); await initProviders(); await loadHistoryPage(0); stopEventStream(); } else { setSession("", null); stopEventStream(); } return; }
        localMode = false;
        try { const data = await fetchJson("/api/auth/me"); setSession(authToken, data.user); await initProviders(); await loadHistoryPage(0); startEventStream(); }
        catch (e) { localMode = await detectLocalMode(); if (localMode) { setAuthError(""); setSession("", { username: "本地模式", role: "user", must_change_password: false, quota: null }); await initProviders(); await loadHistoryPage(0); stopEventStream(); return; } setSession("", null); setAuthError("登录已过期，请重新登录。"); stopEventStream(); }
      }
      async function login() { setAuthError(""); const username = document.getElementById("loginUsername").value.trim(); const password = document.getElementById("loginPassword").value; const data = await fetchJson("/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ username, password }) }); console.log("Login succeeded, token:", data.token ? "present" : "missing"); setSession(data.token, data.user); await initProviders(); await loadHistoryPage(0); startEventStream(); }
      async function registerAccount() { setAuthError(""); const username = document.getElementById("registerUsername").value.trim(); const password = document.getElementById("registerPassword").value; const invite_code = document.getElementById("registerInvite").value.trim(); const data = await fetchJson("/api/auth/register", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ username, password, invite_code }) }); setSession(data.token, data.user); await initProviders(); await loadHistoryPage(0); startEventStream(); }
      function _isRegisterModeNow() { return !(registerPanel && registerPanel.classList.contains("hidden")); }
      async function loadCommunity() {
        // Desktop shows `communityList2`, mobile shows `communityList`.
        const el = _pickContainer(communityListEl2, communityListEl);
        if (!el) return;
        el.innerHTML = '<div class="muted">加载中…</div>';
        let jobs = [];
        if (localMode) {
          const data = await fetchJson("/api/jobs/recent?limit=30");
          jobs = data.jobs || [];
        } else {
          const data = await fetchJson("/api/community");
          jobs = data.jobs || [];
        }
        if (!jobs.length) {
          el.innerHTML = localMode ? '<div class="muted">暂无历史记录。</div>' : '<div class="muted">暂无公开作品。</div>';
          return;
        }
        el.innerHTML = "";
        for (const job of jobs) {
          const item = document.createElement("div");
          item.className = "community-item";
          const _cm = job.metadata || {};
          const titleLine = document.createElement("div");
          titleLine.style.cssText = "display:flex;align-items:center;gap:6px;";
          const infoBtn = document.createElement("button");
          infoBtn.className = "btn btn-secondary btn-sm";
          infoBtn.innerHTML = '<svg class="icon icon-sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>';
          infoBtn.title = "详细信息";
          infoBtn.style.cssText = "flex-shrink:0;padding:2px 4px;";
          infoBtn.addEventListener("click", (e) => { e.stopPropagation(); showSongInfo(job); });
          titleLine.appendChild(infoBtn);
          const title = document.createElement("span");
          title.style.fontWeight = "600";
          title.textContent = _shortText(_cm.title || job.prompt || "未命名作品", 90);
          titleLine.appendChild(title);
          item.appendChild(titleLine);
          const meta = document.createElement("div");
          meta.className = "muted";
          const _metaParts = [];
          if (_cm.author) _metaParts.push(_cm.author);
          if (_cm.album) _metaParts.push(_cm.album);
          _metaParts.push(localMode ? (job.provider || "-") + " · " + (job.status || "-") : (job.provider || "-") + " · " + (job.share_permission === "downloadable" ? "可下载" : "仅试听"));
          meta.textContent = _metaParts.join(" · ");
          item.appendChild(meta);
          if (_cm.tags && _cm.tags.length > 0) { const tagsDiv = document.createElement("div"); tagsDiv.className = "muted"; tagsDiv.style.marginTop = "4px"; for (const tag of _cm.tags.slice(0, 5)) { const sp = document.createElement("span"); sp.style.cssText = "display:inline-block;background:var(--color-bg-card-solid);border:1px solid var(--glass-border);border-radius:999px;padding:1px 8px;margin:2px 4px 2px 0;font-size:12px;"; sp.textContent = tag; tagsDiv.appendChild(sp); } item.appendChild(tagsDiv); }
          if (job.audio_url) {
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "metadata";
            audio.src = job.audio_url;
            audio.style.marginTop = "8px";
            item.appendChild(audio);
          }
          if (!localMode && job.download_url) {
            const link = document.createElement("a");
            link.href = job.download_url;
            link.className = "btn btn-accent btn-sm";
            link.style.marginTop = "8px";
            link.textContent = "下载";
            item.appendChild(link);
          }
          el.appendChild(item);
        }
      }
      function loadHistoryPageSizePref() { try { const raw = localStorage.getItem(HISTORY_PAGE_SIZE_KEY); const n = parseInt(String(raw || ""), 10); if (Number.isFinite(n) && n > 0) return n; } catch {} return 20; }
      function saveHistoryPageSizePref() { try { localStorage.setItem(HISTORY_PAGE_SIZE_KEY, String(historyLimit)); } catch {} }
      function updateHistoryPagerUi() { const totalPages = historyLimit > 0 ? Math.max(1, Math.ceil((historyTotal || 0) / historyLimit)) : 1; const page = historyLimit > 0 ? Math.floor(historyOffset / historyLimit) + 1 : 1; const from = historyTotal === 0 ? 0 : (historyOffset + 1); const to = Math.min(historyOffset + historyLimit, historyTotal); if (historyInfoEl) historyInfoEl.textContent = from + "-" + to + " / " + historyTotal + "（第 " + page + "/" + totalPages + " 页）"; if (historyInfoEl2) historyInfoEl2.textContent = from + "-" + to + " / " + historyTotal + "（第 " + page + "/" + totalPages + " 页）"; if (historyPrevBtn) historyPrevBtn.disabled = historyOffset <= 0; if (historyNextBtn) historyNextBtn.disabled = (historyOffset + historyLimit) >= historyTotal; if (historyPrevBtn2) historyPrevBtn2.disabled = historyOffset <= 0; if (historyNextBtn2) historyNextBtn2.disabled = (historyOffset + historyLimit) >= historyTotal; }
      async function loadHistoryPage(offset) {
        const off = Math.max(0, parseInt(String(offset || "0"), 10) || 0); historyOffset = off; updateHistoryPagerUi();
        try {
          const data = await fetchJson("/api/jobs/history?offset=" + historyOffset + "&limit=" + historyLimit);
          historyJobs = data.jobs || [];
          historyTotal = parseInt(String(data.total || "0"), 10) || 0;
          historyOffset = parseInt(String(data.offset || historyOffset), 10) || historyOffset;
          historyLimit = parseInt(String(data.limit || historyLimit), 10) || historyLimit;
          if (historyPageSizeEl) historyPageSizeEl.value = String(historyLimit);
          if (historyPageSizeEl2) historyPageSizeEl2.value = String(historyLimit);
          renderList(historyJobs);
          const active = new Set((historyJobs || []).map(j => (j && j.audio_url) ? String(j.audio_url) : "").filter(Boolean));
          if (currentMainAudioUrl) active.add(String(currentMainAudioUrl));
          cleanupUnusedAudioBlobUrls(active);
        } finally { updateHistoryPagerUi(); }
      }
      function getSelectedProviderId() {
        const def = providersMeta && providersMeta.default_provider ? String(providersMeta.default_provider) : "";
        return (def || DEFAULT_PROVIDER_ID).trim();
      }
      function getProviderMeta(id) { if (!providersMeta || !providersMeta.providers) return null; return providersMeta.providers.find(p => p.id === id) || null; }
      function toBool(v) { if (v === true || v === false) return v; if (typeof v === "string") return v === "true" || v === "1" || v === "on"; return Boolean(v); }
      function shouldShowField(field, values) {
        const cond = field.visible_if; if (!cond) return true;
        for (const k of Object.keys(cond)) {
          const expected = cond[k];
          const actual = values[k];
          if (Array.isArray(expected)) { if (!expected.includes(actual)) return false; }
          else { if (actual !== expected) return false; }
        }
        return true;
      }
      function _readAudioAsB64(file) { return new Promise((resolve, reject) => { if (!file) return resolve(null); if (file.size > 20 * 1024 * 1024) { reject(new Error("音频文件不能超过 20MB")); return; } const reader = new FileReader(); reader.onload = () => { const dataUrl = reader.result; const commaIdx = dataUrl.indexOf(","); if (commaIdx < 0) { reject(new Error("无法读取音频文件")); return; } const b64 = dataUrl.substring(commaIdx + 1); resolve(b64); }; reader.onerror = () => reject(new Error("读取音频文件失败")); reader.readAsDataURL(file); }); }
      async function _uploadAudioFile(file) { if (!file) return null; if (!authToken) throw new Error("请先登录再上传音频文件"); if (file.size > 20 * 1024 * 1024) throw new Error("音频文件不能超过 20MB"); const fd = new FormData(); fd.append("file", file); const res = await fetch("/api/uploads/audio", { method: "POST", headers: { Authorization: "Bearer " + authToken }, body: fd }); const text = await res.text().catch(() => ""); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; } if (!res.ok) { throw new Error(formatApiError(data, text || "HTTP " + res.status)); } return data; }
      function _audioFormatFromFile(file) { if (!file) return "mp3"; const name = file.name.toLowerCase(); if (name.endsWith(".wav")) return "wav"; if (name.endsWith(".flac")) return "flac"; return "mp3"; }
      function clearAudioInput(which) {
        if (which === "src") {
          srcAudioUploadId = null; srcAudioB64 = null; srcAudioFormat = null;
          if (srcAudioInput) srcAudioInput.value = "";
          if (srcAudioInputMobile) srcAudioInputMobile.value = "";
          if (srcAudioInfo) { srcAudioInfo.style.display = "none"; srcAudioInfo.querySelector(".file-name").textContent = ""; }
          if (srcAudioInfoMobile) { srcAudioInfoMobile.style.display = "none"; srcAudioInfoMobile.querySelector(".file-name").textContent = ""; }
        } else {
          refAudioUploadId = null; refAudioB64 = null; refAudioFormat = null;
          if (refAudioInput) refAudioInput.value = "";
          if (refAudioInputMobile) refAudioInputMobile.value = "";
          if (refAudioInfo) { refAudioInfo.style.display = "none"; refAudioInfo.querySelector(".file-name").textContent = ""; }
          if (refAudioInfoMobile) { refAudioInfoMobile.style.display = "none"; refAudioInfoMobile.querySelector(".file-name").textContent = ""; }
        }
      }
      async function handleAudioFileInput(which, file) {
        if (!file) return;
        try {
          const infoEl = (which === "src") ? srcAudioInfo : refAudioInfo;
          const infoElMobile = (which === "src") ? srcAudioInfoMobile : refAudioInfoMobile;
          const fmt = _audioFormatFromFile(file);
          if (localMode) {
            const b64 = await _readAudioAsB64(file);
            if (which === "src") { srcAudioUploadId = null; srcAudioB64 = b64; srcAudioFormat = fmt; }
            else { refAudioUploadId = null; refAudioB64 = b64; refAudioFormat = fmt; }
          } else {
            const up = await _uploadAudioFile(file);
            const uploadId = up && up.upload_id ? String(up.upload_id) : null;
            const serverFmt = up && up.format ? String(up.format) : fmt;
            if (!uploadId) throw new Error("上传失败：未返回 upload_id");
            if (which === "src") { srcAudioUploadId = uploadId; srcAudioB64 = null; srcAudioFormat = serverFmt; }
            else { refAudioUploadId = uploadId; refAudioB64 = null; refAudioFormat = serverFmt; }
          }
          if (infoEl) { infoEl.style.display = "flex"; infoEl.querySelector(".file-name").textContent = file.name; }
          if (infoElMobile) { infoElMobile.style.display = "flex"; infoElMobile.querySelector(".file-name").textContent = file.name; }
        } catch (e) {
          const msg = (e && e.message) ? e.message : String(e || "");
          setError("音频文件处理失败: " + msg);
          clearAudioInput(which);
        }
      }
      function parseFieldValue(field, raw) { if (field.kind === "boolean") return toBool(raw); if (field.kind === "integer") return raw === "" || raw === null ? null : parseInt(raw, 10); if (field.kind === "number") return raw === "" || raw === null ? null : parseFloat(raw); if (field.kind === "json") { if (raw === "" || raw === null) return null; try { return JSON.parse(raw); } catch { return raw; } } return raw === "" ? null : raw; }
      function _ensureFieldBadge(labelEl, kind) { if (!labelEl) return; const existing = labelEl.querySelector(".field-badge"); if (existing) existing.remove(); const badge = document.createElement("span"); badge.className = "field-badge " + kind; badge.textContent = (kind === "required") ? "必填" : "可选"; labelEl.appendChild(badge); }
      function _decorateStaticBadges() { const mapping = [{ id: "advanced", kind: "optional" }, { id: "duration", kind: "required" }, { id: "vocals", kind: "required" }, { id: "lyrics", kind: "optional" }, { id: "seed", kind: "optional" }]; for (const m of mapping) { const label = document.querySelector("label[for=\"" + m.id + "\"]"); _ensureFieldBadge(label, m.kind); } const promptLabel = document.querySelector("label[for=\"prompt\"]"); _ensureFieldBadge(promptLabel, "required"); }
      function _isCompositionPlanProvidedNow() { return false; }
      function _updatePromptBadge() { const label = document.querySelector("label[for=\"prompt\"]"); const optional = _isCompositionPlanProvidedNow(); _ensureFieldBadge(label, optional ? "optional" : "required"); }
      function _clearValidationUi() { document.querySelectorAll(".field-error-msg").forEach(n => n.remove()); document.querySelectorAll(".input-error").forEach(n => n.classList.remove("input-error")); }
      function _setFieldError(el, msg, opts) {
        if (!el) return;
        el.classList.add("input-error");
        const m = document.createElement("div");
        m.className = "field-error-msg";
        m.textContent = msg;
        let anchor = (opts && opts.anchor) ? opts.anchor : el;
        // If the element lives inside a flex row (e.g. textarea + buttons),
        // inserting the error node next to it will shrink the input. Instead,
        // attach the message after the flex container so layout stays stable.
        try {
          const p = anchor && anchor.parentElement ? anchor.parentElement : null;
          if (p) {
            const disp = window.getComputedStyle(p).display;
            if (disp === "flex" || disp === "inline-flex") {
              anchor = p;
            }
          }
        } catch {}
        anchor.insertAdjacentElement("afterend", m);
      }
      function _focusField(el) { try { if (!el) return; el.scrollIntoView({ behavior: "smooth", block: "center" }); if (typeof el.focus === "function") el.focus(); } catch {} }
      function _validateGenerateCommon(payload, opts) {
        _clearValidationUi(); _updatePromptBadge();
        const providerId = String(payload.provider || getSelectedProviderId() || "").trim();
        const meta = providerId ? getProviderMeta(providerId) : null;
        const errors = []; let firstEl = null;
        function fail(el, msg, extra) { errors.push(msg); if (!firstEl && el) firstEl = el; _setFieldError(el, msg, extra); }
        if (!providerId) { setError("Provider 尚未初始化，请刷新页面后重试。"); setStatus(""); return false; }
        if (!meta) { setError("Provider 列表尚未加载完成，请稍后再试。"); setStatus(""); return false; }
        if (meta && meta.ready === false) { const missing = Array.isArray(meta.missing_env) ? meta.missing_env.join(", ") : ""; setError("该 provider 未配置密钥，无法生成。\n缺少：" + (missing || "(unknown)")); setStatus(""); return false; }
        const promptVal = String(payload.prompt || "").trim();
        if (!promptVal) { fail(promptEl, "请填写 Prompt（必填）。"); }
        const duration = parseInt(String(payload.duration_sec != null ? payload.duration_sec : ""), 10);
        if (!Number.isFinite(duration) || duration < 3 || duration > 600) { const anchor = durationSlider ? durationSlider.parentElement : null; fail(durationSlider, "时长建议 3–600 秒。", { anchor: anchor || durationSlider }); }
        const seedEl = document.getElementById("seed"); const seedRaw = seedEl ? String(seedEl.value || "").trim() : "";
        if (seedRaw) { const seed = parseInt(seedRaw, 10); if (!Number.isFinite(seed) || seed < 0 || seed > 2147483647) { fail(seedEl, "Seed 必须是 0–2147483647 的整数，或留空。"); } }
        if (meta && Array.isArray(meta.fields)) { for (const field of meta.fields) { if (!field || field.required !== true) continue; const input = providerFieldsEl.querySelector("[data-key=\"" + field.key + "\"]"); if (!input) continue; if (input.tagName === "INPUT" && input.type === "checkbox") { if (!input.checked) fail(input, field.label + "：必填。"); continue; } const raw = String(input.value != null ? input.value : ""); if (!raw.trim()) { fail(input, field.label + "：必填。"); continue; } if (field.kind === "integer") { const n = parseInt(raw, 10); if (!Number.isFinite(n)) fail(input, field.label + "：请输入整数。"); } else if (field.kind === "number") { const n = parseFloat(raw); if (!Number.isFinite(n)) fail(input, field.label + "：请输入数字。"); } else if (field.kind === "json") { try { const parsed = JSON.parse(raw); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) { fail(input, field.label + "：必须是 JSON 对象。"); } } catch { fail(input, field.label + "：JSON 格式不合法。"); } } } }
        if (errors.length > 0) { setError("请补全必填项后再提交：\n- " + errors.join("\n- ")); setStatus(""); _focusField(firstEl); return false; }
        return true;
      }
      function shouldShowLyricsInputForProvider(providerId) { return true; }
      function shouldShowLyricsInput() { return shouldShowLyricsInputForProvider(getSelectedProviderId()); }
      function updateLyricsUi() {
        if (!lyricsRowEl) return;
        const show = !_isOriginalSimpleMode() && shouldShowLyricsInput();
        lyricsRowEl.style.display = show ? "" : "none";
        const hintMobile = document.getElementById("lyricsHintMobile");
        if (!lyricsHintEl && !hintMobile) return;
        if (!show) { if (lyricsHintEl) { lyricsHintEl.style.display = "none"; lyricsHintEl.textContent = ""; } if (hintMobile) { hintMobile.style.display = "none"; hintMobile.textContent = ""; } return; }
        const providerId = getSelectedProviderId();
        let hintText = "";
        if (providerId === "acestep") { hintText = "ACE-Step：支持 50+ 语言歌词，可用 [Verse] [Chorus] [Bridge] 等标签组织段落结构。"; }
        if (lyricsHintEl) { lyricsHintEl.style.display = hintText ? "block" : "none"; lyricsHintEl.textContent = hintText; }
        if (hintMobile) { hintMobile.style.display = hintText ? "block" : "none"; hintMobile.textContent = hintText; }
      }
      function getLyricsPayloadValue(providerOverride) { const pid = providerOverride ? String(providerOverride).trim() : getSelectedProviderId(); if (!shouldShowLyricsInputForProvider(pid)) return null; const val = (lyricsEl && lyricsEl.value ? lyricsEl.value : "").trim(); return val ? val : null; }
      durationSlider.addEventListener("input", () => { durationValue.textContent = durationSlider.value + " 秒"; });
      document.getElementById("quickGenreTags").addEventListener("click", (e) => { const tag = e.target.closest(".tag"); if (tag) { const genre = tag.dataset.genre; if (promptEl.value.trim()) { promptEl.value = promptEl.value.trim() + "，" + genre; } else { promptEl.value = genre; } document.querySelectorAll("#quickGenreTags .tag").forEach(t => t.classList.remove("active")); tag.classList.add("active"); setTimeout(() => tag.classList.remove("active"), 500); } });
      function renderTags(containerId, tags, removeFn) { const container = document.getElementById(containerId); container.innerHTML = tags.map((tag, i) => '<span class="cp-tag">' + tag + '<span class="cp-tag-remove" onclick="' + removeFn + '(' + i + ')">×</span></span>').join(""); }
      function addPositiveStyle() { const input = document.getElementById("positiveStyleInput"); const val = input.value.trim(); if (val && !cpState.positive_global_styles.includes(val)) { cpState.positive_global_styles.push(val); renderTags("positiveStyles", cpState.positive_global_styles, "removePositiveStyle"); } input.value = ""; }
      function removePositiveStyle(i) { cpState.positive_global_styles.splice(i, 1); renderTags("positiveStyles", cpState.positive_global_styles, "removePositiveStyle"); }
      function addNegativeStyle() { const input = document.getElementById("negativeStyleInput"); const val = input.value.trim(); if (val && !cpState.negative_global_styles.includes(val)) { cpState.negative_global_styles.push(val); renderTags("negativeStyles", cpState.negative_global_styles, "removeNegativeStyle"); } input.value = ""; }
      function removeNegativeStyle(i) { cpState.negative_global_styles.splice(i, 1); renderTags("negativeStyles", cpState.negative_global_styles, "removeNegativeStyle"); }
      function addPresetStyle(type, style) { if (type === "positive" && !cpState.positive_global_styles.includes(style)) { cpState.positive_global_styles.push(style); renderTags("positiveStyles", cpState.positive_global_styles, "removePositiveStyle"); } else if (type === "negative" && !cpState.negative_global_styles.includes(style)) { cpState.negative_global_styles.push(style); renderTags("negativeStyles", cpState.negative_global_styles, "removeNegativeStyle"); } }
      function setBpm(val) { document.getElementById("cpBpm").value = val; }
      function setKey(val) { document.getElementById("cpKey").value = val; }
      function addSection(type) { const section = { local_styles: type ? [type] : [], duration_ms: type ? getDefaultDurationForType(type) : null, lyrics: "" }; cpState.sections.push(section); renderSections(); }
      function getDefaultDurationForType(type) { const defaults = { "intro": 15000, "verse": 30000, "chorus": 30000, "bridge": 20000, "outro": 15000 }; return defaults[type] || null; }
      function removeSection(i) { cpState.sections.splice(i, 1); renderSections(); }
      function moveSection(i, direction) { const newIndex = i + direction; if (newIndex < 0 || newIndex >= cpState.sections.length) return; const temp = cpState.sections[i]; cpState.sections[i] = cpState.sections[newIndex]; cpState.sections[newIndex] = temp; renderSections(); }
      function formatTime(ms) { if (!ms) return "--:--"; const totalSec = Math.floor(ms / 1000); const min = Math.floor(totalSec / 60); const sec = totalSec % 60; return min + ":" + sec.toString().padStart(2, "0"); }
      function getTotalDuration() { return cpState.sections.reduce((sum, sec) => sum + (sec.duration_ms || 0), 0); }
      function getSectionType(sec) { const styles = sec.local_styles || []; const typeOrder = ["intro", "verse", "chorus", "bridge", "outro"]; for (const t of typeOrder) { if (styles.includes(t)) return t; } return "custom"; }
      function renderSections() {
        const container = document.getElementById("sectionsContainer");
        if (cpState.sections.length === 0) { container.innerHTML = '<p style="margin-top:var(--space-md);font-size:13px;color:var(--color-text-muted);">点击上方按钮添加段落（Intro/Verse/Chorus 等）</p>'; updateTimeline(); return; }
        let startMs = 0;
        const sectionsWithTime = cpState.sections.map(sec => { const info = { ...sec, startMs }; startMs += sec.duration_ms || 0; return info; });
        const sectionTypes = ["intro", "verse", "chorus", "bridge", "outro"];
        container.innerHTML = sectionsWithTime.map((sec, i) => {
          const sectionType = getSectionType(sec);
          return '<div class="cp-section" draggable="true" data-index="' + i + '"><div class="cp-section-header"><span class="cp-section-title"><span class="cp-section-drag">⋮⋮</span>段落 ' + (i + 1) + '<span class="cp-section-time">' + formatTime(sec.startMs) + " - " + formatTime(sec.startMs + (sec.duration_ms || 0)) + '</span></span><div class="cp-section-actions"><button class="cp-section-move" onclick="moveSection(' + i + ',-1)" ' + (i === 0 ? "disabled" : "") + '>↑</button><button class="cp-section-move" onclick="moveSection(' + i + ',1)" ' + (i === cpState.sections.length - 1 ? "disabled" : "") + '>↓</button><button class="cp-section-remove" onclick="removeSection(' + i + ')">删除</button></div></div><div class="cp-row"><div><label>类型/风格</label><div id="sectionStyles' + i + '" class="cp-tags"></div><div class="cp-add-tag"><input type="text" id="sectionStyleInput' + i + '" placeholder="例如：energetic, emotional" onkeypress="if(event.key===\'Enter\'){event.preventDefault();addSectionStyle(' + i + ');}"><button class="btn btn-secondary btn-sm" onclick="addSectionStyle(' + i + ')">添加</button></div><div class="cp-presets">' + sectionTypes.map(t => '<button class="cp-preset-btn ' + (sectionType === t ? "active" : "") + '" onclick="setSectionType(' + i + ',\'' + t + '\')">' + t.charAt(0).toUpperCase() + t.slice(1) + '</button>').join("") + '</div></div><div><label>时长（秒）</label><input type="number" min="3" max="120" value="' + (sec.duration_ms ? sec.duration_ms / 1000 : "") + '" onchange="updateSectionDuration(' + i + ',this.value)" placeholder="留空则自动"></div></div><div style="margin-top:var(--space-sm);"><label>歌词（可选）</label><textarea style="min-height:60px;" placeholder="在此段歌词..." onchange="updateSectionLyrics(' + i + ',this.value)">' + (sec.lyrics || "") + '</textarea></div></div>';
        }).join("");
        cpState.sections.forEach((sec, i) => { renderSectionTags(i); });
        setupDragAndDrop(); updateTimeline();
      }
      function setupDragAndDrop() {
        const sections = document.querySelectorAll(".cp-section");
        sections.forEach(section => {
          section.addEventListener("dragstart", (e) => { draggedSection = section; section.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
          section.addEventListener("dragend", () => { section.classList.remove("dragging"); document.querySelectorAll(".cp-section").forEach(s => s.classList.remove("drag-over")); draggedSection = null; });
          section.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; if (draggedSection && draggedSection !== section) { section.classList.add("drag-over"); } });
          section.addEventListener("dragleave", () => { section.classList.remove("drag-over"); });
          section.addEventListener("drop", (e) => { e.preventDefault(); section.classList.remove("drag-over"); if (draggedSection && draggedSection !== section) { const fromIndex = parseInt(draggedSection.dataset.index); const toIndex = parseInt(section.dataset.index); const item = cpState.sections.splice(fromIndex, 1)[0]; cpState.sections.splice(toIndex, 0, item); renderSections(); } });
        });
      }
      function updateTimeline() {
        const timeline = document.getElementById("timeline");
        if (cpState.sections.length === 0) { timeline.style.display = "none"; return; }
        timeline.style.display = "flex";
        let currentMs = 0;
        const segments = cpState.sections.map((sec, i) => { const type = getSectionType(sec); const duration = sec.duration_ms || 0; const start = currentMs; currentMs += duration; return '<div class="cp-timeline-segment ' + type + '" onclick="scrollToSection(' + i + ')">' + (type || "段落 " + (i + 1)) + " (" + formatTime(duration) + ")</div>"; }).join("");
        timeline.innerHTML = '<span style="font-size:13px;color:var(--color-text-secondary);">时间轴：</span>' + segments + '<span class="cp-timeline-total">总计: ' + formatTime(getTotalDuration()) + "</span>";
      }
      function scrollToSection(i) { const sections = document.querySelectorAll(".cp-section"); if (sections[i]) { sections[i].scrollIntoView({ behavior: "smooth", block: "center" }); sections[i].style.outline = "2px solid var(--color-accent)"; setTimeout(() => { sections[i].style.outline = ""; }, 1000); } }
      function setSectionType(i, type) { const sec = cpState.sections[i]; const typeOrder = ["intro", "verse", "chorus", "bridge", "outro"]; sec.local_styles = sec.local_styles.filter(s => !typeOrder.includes(s)); sec.local_styles.unshift(type); if (!sec.duration_ms) { sec.duration_ms = getDefaultDurationForType(type); } renderSections(); }
      function addSectionStyle(i) { const input = document.getElementById("sectionStyleInput" + i); const val = input.value.trim(); if (val && !cpState.sections[i].local_styles.includes(val)) { cpState.sections[i].local_styles.push(val); renderSectionTags(i); } input.value = ""; }
      function removeSectionStyle(i, j) { cpState.sections[i].local_styles.splice(j, 1); renderSectionTags(i); updateTimeline(); }
      function renderSectionTags(i) { const container = document.getElementById("sectionStyles" + i); if (!container) return; container.innerHTML = cpState.sections[i].local_styles.map((tag, j) => '<span class="cp-tag">' + tag + '<span class="cp-tag-remove" onclick="removeSectionStyle(' + i + "," + j + ')">×</span></span>').join(""); }
      function updateSectionDuration(i, val) { const sec = parseInt(val, 10); cpState.sections[i].duration_ms = sec > 0 ? sec * 1000 : null; renderSections(); }
      function updateSectionLyrics(i, val) { cpState.sections[i].lyrics = val.trim() || ""; }
      function applyGenrePreset(genre) {
        clearCompositionPlan();
        const presets = {
          pop: { positive_global_styles: ["synths", "drums", "bass"], bpm: 120, sections: [{ local_styles: ["intro"], duration_ms: 15000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 30000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 30000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 30000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 30000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 15000, lyrics: "" }] },
          ballad: { positive_global_styles: ["piano", "strings"], bpm: 70, sections: [{ local_styles: ["intro"], duration_ms: 20000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 40000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 45000, lyrics: "" }, { local_styles: ["bridge"], duration_ms: 30000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 45000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 20000, lyrics: "" }] },
          electronic: { positive_global_styles: ["synths", "drums", "bass"], bpm: 128, sections: [{ local_styles: ["intro"], duration_ms: 30000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 30000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 45000, lyrics: "" }, { local_styles: ["bridge"], duration_ms: 20000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 45000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 30000, lyrics: "" }] },
          rock: { positive_global_styles: ["electric guitar", "drums", "bass"], bpm: 110, sections: [{ local_styles: ["intro"], duration_ms: 15000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 25000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 30000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 25000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 30000, lyrics: "" }, { local_styles: ["bridge"], duration_ms: 25000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 30000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 15000, lyrics: "" }] },
          ambient: { positive_global_styles: ["synths", "strings"], bpm: 60, sections: [{ local_styles: ["intro"], duration_ms: 60000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 90000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 60000, lyrics: "" }] },
          guofeng: { positive_global_styles: ["guzheng", "erhu", "dizi", "pipa", "strings"], bpm: 90, sections: [{ local_styles: ["intro"], duration_ms: 20000, lyrics: "" }, { local_styles: ["verse"], duration_ms: 35000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 35000, lyrics: "" }, { local_styles: ["bridge"], duration_ms: 25000, lyrics: "" }, { local_styles: ["chorus"], duration_ms: 35000, lyrics: "" }, { local_styles: ["outro"], duration_ms: 20000, lyrics: "" }] }
        };
        const preset = presets[genre];
        if (preset) { cpState.positive_global_styles = [...preset.positive_global_styles]; cpState.sections = preset.sections.map(s => ({ ...s })); document.getElementById("cpBpm").value = preset.bpm; renderTags("positiveStyles", cpState.positive_global_styles, "removePositiveStyle"); renderSections(); }
      }
      function clearCompositionPlan() { cpState = { positive_global_styles: [], negative_global_styles: [], sections: [], bpm: null, key: null }; document.getElementById("cpBpm").value = ""; document.getElementById("cpKey").value = ""; renderTags("positiveStyles", [], "removePositiveStyle"); renderTags("negativeStyles", [], "removeNegativeStyle"); renderSections(); }
      function buildCompositionPlan() {
        const bpm = parseInt(document.getElementById("cpBpm").value, 10); const key = document.getElementById("cpKey").value.trim(); const plan = {};
        if (cpState.positive_global_styles.length > 0) { plan.positive_global_styles = cpState.positive_global_styles; }
        if (cpState.negative_global_styles.length > 0) { plan.negative_global_styles = cpState.negative_global_styles; }
        if (bpm > 0) { plan.bpm = bpm; }
        if (key) { plan.key = key; }
        if (cpState.sections.length > 0) { plan.sections = cpState.sections.map(sec => { const s = {}; if (sec.local_styles.length > 0) { s.local_styles = sec.local_styles; } if (sec.duration_ms) { s.duration_ms = sec.duration_ms; } if (sec.lyrics) { s.lyrics = sec.lyrics; } return s; }); }
        return Object.keys(plan).length > 0 ? plan : null;
      }
      function collectProviderParams() {
        const meta = getProviderMeta(getSelectedProviderId()); if (!meta) return {}; const params = {};
        for (const field of (meta.fields || [])) { const input = providerFieldsEl.querySelector("[data-key=\"" + field.key + "\"]"); if (!input) continue; const raw = (input.type === "checkbox") ? input.checked : input.value; params[field.key] = parseFieldValue(field, raw); }
        if (!params.use_composition_plan) delete params.composition_plan_json;
        if (!localMode && srcAudioUploadId) { params.src_audio_upload_id = srcAudioUploadId; params.src_audio_format = srcAudioFormat || "mp3"; } else if (localMode && srcAudioB64) { params.src_audio_b64 = srcAudioB64; params.src_audio_format = srcAudioFormat || "mp3"; }
        if (!localMode && refAudioUploadId) { params.reference_audio_upload_id = refAudioUploadId; params.reference_audio_format = refAudioFormat || "mp3"; } else if (localMode && refAudioB64) { params.reference_audio_b64 = refAudioB64; params.reference_audio_format = refAudioFormat || "mp3"; }
        return params;
      }
      function renderProviderFields(opts) {
        const reset = Boolean(opts && opts.reset);
        const providerId = getSelectedProviderId(); const meta = getProviderMeta(providerId);
        if (!meta) { providerFieldsEl.innerHTML = '<div class="err">Provider 不存在：' + providerId + '</div>'; return; }
        const caps = meta.capabilities || {}; const vocalsSelect = document.getElementById("vocals");
        if (caps.supports_vocals === false) { vocalsSelect.value = "off"; vocalsSelect.disabled = true; } else { vocalsSelect.disabled = false; }
        const advancedMode = advancedEl.value === "advanced";
        // Composition plan editor is for a provider flow we don't support on the backend today.
        cpEditorEl.classList.remove("visible");
        const values = {};
        for (const field of (meta.fields || [])) {
          const raw = field.default != null ? field.default : null;
          values[field.key] = (field.kind === "boolean") ? toBool(raw) : raw;
        }
        if (!reset) {
          for (const field of (meta.fields || [])) {
            const existing = providerFieldsEl.querySelector("[data-key=\"" + field.key + "\"]");
            if (existing) { values[field.key] = (existing.type === "checkbox") ? Boolean(existing.checked) : existing.value; }
          }
        }
        // Mode-based behavior:
        // - Original/simple: hide all optional provider params and force task_type=text2music.
        // - Remix: expose task_type (without text2music) and default it based on remix sub-mode.
        const isOriginal = !_isRemixMode();
        if (isOriginal) values.task_type = "text2music";
        if (_isRemixMode()) values.task_type = reset ? _preferredRemixTaskType() : (values.task_type || _preferredRemixTaskType());
        const effectiveTaskType = String(values.task_type || "text2music");

        let html = "";
        const isMobileViewport = !_isDesktopViewport();
        const showMetaBlock = !_isOriginalSimpleMode();
        if (showMetaBlock) {
          const descRaw = meta.description || "";
          const desc = isMobileViewport ? _shortText(descRaw, 80) : descRaw;
          html += '<div class="provider-desc" style="font-size:13px;color:var(--color-text-secondary);margin-bottom:var(--space-sm);word-break:break-word;line-height:1.35;">' + desc + '</div>';
          if (meta.ready === false) { html += '<div class="err">未配置该 provider 的密钥：<span class="mono">' + JSON.stringify(meta.missing_env || []) + '</span></div>'; }
          if (!isMobileViewport) {
            html += '<div style="font-size:12px;color:var(--color-text-muted);margin-top:var(--space-xs);">能力信息：<span class="mono">' + JSON.stringify(meta.capabilities || {}) + '</span></div>';
          }
        }

        let fields = (meta.fields || []).filter(f => advancedMode || !f.advanced);
        if (_isOriginalSimpleMode()) fields = fields.filter(f => f.required === true);
        // task_type is not meaningful for original mode; it's always text2music there.
        if (!_isRemixMode()) fields = fields.filter(f => f.key !== "task_type");
        // Remix mode: show task_type even though it's optional, and exclude text2music.
        if (_isRemixMode()) {
          const hasTaskType = fields.some(f => f.key === "task_type");
          if (!hasTaskType) {
            const fromMeta = (meta.fields || []).find(f => f && f.key === "task_type");
            if (fromMeta) fields = [fromMeta, ...fields];
          }
        }

        // Hide task-specific knobs unless they match the effective task_type.
        // This prevents "original/advanced" UI from showing remix-oriented fields.
        const hideKeys = new Set();
        if (isOriginal) {
          hideKeys.add("audio_cover_strength");
          hideKeys.add("repainting_start");
          hideKeys.add("repainting_end");
        } else {
          if (effectiveTaskType !== "cover") hideKeys.add("audio_cover_strength");
          if (!(effectiveTaskType === "repaint" || effectiveTaskType === "lego")) {
            hideKeys.add("repainting_start");
            hideKeys.add("repainting_end");
          }
        }
        fields = fields.filter(f => !hideKeys.has(f.key));

        for (const field of fields) {
          if (!shouldShowField(field, values)) continue;
          html += '<label>' + field.label + '<span class="field-badge ' + (field.required ? "required" : "optional") + '">' + (field.required ? "必填" : "可选") + '</span></label>';
          if (field.kind === "enum" && Array.isArray(field.enum)) {
            const _enumLabels = { "zh": "中文 (zh)", "en": "英文 (en)", "ja": "日语 (ja)", "ko": "韩语 (ko)", "auto": "自动识别" };
            const enumVals = (field.key === "task_type" && _isRemixMode())
              ? field.enum.filter(x => String(x) !== "text2music")
              : field.enum;
            html += '<select data-key="' + field.key + '">';
            for (const opt of enumVals) {
              const selected = (String(opt) === String(values[field.key])) ? "selected" : "";
              const display = (opt === "") ? "自动推断" : (_enumLabels[opt] || opt);
              html += '<option value="' + opt + '" ' + selected + '>' + display + '</option>';
            }
            html += '</select>';
          } else if (field.kind === "boolean") {
            const checked = values[field.key] ? "checked" : "";
            html += '<div style="display:flex;align-items:flex-start;gap:var(--space-sm);margin-top:var(--space-xs);"><input type="checkbox" data-key="' + field.key + '" ' + checked + '> <span style="font-size:13px;color:var(--color-text-secondary);line-height:1.35;flex:1;word-break:break-word;">' + (field.help || "") + '</span></div>';
            continue;
          } else if (field.kind === "json") {
            html += '<textarea data-key="' + field.key + '" placeholder="粘贴 JSON（高级）"></textarea>';
          } else if (field.kind === "integer") {
            html += '<input type="number" step="1" data-key="' + field.key + '" value="' + (values[field.key] != null ? values[field.key] : "") + '">';
          } else if (field.kind === "number") {
            html += '<input type="number" step="any" data-key="' + field.key + '" value="' + (values[field.key] != null ? values[field.key] : "") + '">';
          } else {
            html += '<input type="text" data-key="' + field.key + '" value="' + (values[field.key] != null ? values[field.key] : "") + '">';
          }
          if (field.help && field.kind !== "boolean") html += '<div style="font-size:12px;color:var(--color-text-muted);margin-top:var(--space-xs);">' + field.help + '</div>';
        }
        providerFieldsEl.innerHTML = html;
        if (providerFieldsMobileEl) { providerFieldsMobileEl.innerHTML = html; providerFieldsMobileEl.style.display = html.trim() ? "" : "none"; for (const field of (meta.fields || [])) { const el = providerFieldsMobileEl.querySelector("[data-key=\"" + field.key + "\"]"); if (!el) continue; const v = values[field.key]; if (el.tagName === "INPUT" && el.type === "checkbox") { el.checked = toBool(v); } else if (v !== null && v !== undefined) { el.value = String(v); } } providerFieldsMobileEl.querySelectorAll("input,select,textarea").forEach(el => { el.addEventListener("change", () => { renderProviderFields(); }); }); }
        // Hide the whole section when it's empty (e.g. original/simple mode).
        providerFieldsEl.style.display = html.trim() ? "" : "none";
        for (const field of (meta.fields || [])) { const el = providerFieldsEl.querySelector("[data-key=\"" + field.key + "\"]"); if (!el) continue; const v = values[field.key]; if (el.tagName === "INPUT" && el.type === "checkbox") { el.checked = toBool(v); } else if (v !== null && v !== undefined) { el.value = String(v); } }
        providerFieldsEl.querySelectorAll("input,select,textarea").forEach(el => { el.addEventListener("change", () => { renderProviderFields(); }); });
        updateLyricsUi(); updateRandomButtonsVisibility(); _updatePromptBadge();
        if (audioUploadSection || audioUploadSectionMobile) {
          const caps = meta.capabilities || {};
          const taskTypeEl = providerFieldsEl.querySelector("[data-key=\"task_type\"]");
          const taskType = taskTypeEl ? taskTypeEl.value : "text2music";
          const show = caps.supports_audio_input && taskType !== "text2music";
          if (audioUploadSection) audioUploadSection.classList.toggle("visible", show);
          if (audioUploadSectionMobile) audioUploadSectionMobile.classList.toggle("visible", show);
          if (!show) { clearAudioInput("src"); clearAudioInput("ref"); }
        }
        // In original/simple mode, keep the UI focused on required fields only.
        const seedEl = document.getElementById("seed");
        if (seedEl) {
          const seedGroup = seedEl.closest(".form-group");
          if (seedGroup) seedGroup.style.display = _isOriginalSimpleMode() ? "none" : "";
          if (_isOriginalSimpleMode()) seedEl.value = "";
        }
        if (seedMobileEl) {
          const seedGroup = seedMobileEl.closest(".form-group");
          if (seedGroup) seedGroup.style.display = _isOriginalSimpleMode() ? "none" : "";
          if (_isOriginalSimpleMode()) seedMobileEl.value = "";
        }
        const advancedGroup = advancedEl ? advancedEl.closest(".form-group") : null;
        // Original advanced mode already implies "show all options", so the extra mode selector is redundant.
        if (advancedGroup) advancedGroup.style.display = "none";

        // Simple mode: enforce defaults and hide non-essential knobs outside provider fields.
        const countEl = document.getElementById("count");
        if (countEl) {
          if (_isOriginalSimpleMode()) { countEl.value = "1"; }
          countEl.style.display = _isOriginalSimpleMode() ? "none" : "";
        }
        if (countMobileEl) {
          if (_isOriginalSimpleMode()) { countMobileEl.value = "1"; }
          countMobileEl.style.display = _isOriginalSimpleMode() ? "none" : "";
        }
        if (_isOriginalSimpleMode() && lyricsEl) lyricsEl.value = "";
        if (_isOriginalSimpleMode() && lyricsMobileEl) lyricsMobileEl.value = "";
        if (lyricsMobileEl) {
          const lyricsGroup = lyricsMobileEl.closest(".form-group");
          const show = !_isOriginalSimpleMode() && shouldShowLyricsInputForProvider(getSelectedProviderId());
          if (lyricsGroup) lyricsGroup.style.display = show ? "" : "none";
        }
      }
      async function initProviders() {
        try {
          providersMeta = await fetchJson("/api/providers");
          const ps = providersMeta.providers || [];
          const def = (providersMeta && providersMeta.default_provider) ? String(providersMeta.default_provider) : "";
          const expected = def || DEFAULT_PROVIDER_ID;
          const meta = ps.find(p => p && p.id === expected) || ps.find(p => p && p.id === DEFAULT_PROVIDER_ID) || ps[0] || null;
          if (!meta || !meta.id) throw new Error("未找到可用 provider");
          providersMeta.default_provider = String(meta.id);
          _syncModeDataset();
          renderProviderFields({ reset: true });
          updateLyricsUi();
          renderSections();
        } catch (e) {
          providerFieldsEl.innerHTML = '<div class="err">加载 provider 失败：' + String(e) + '</div>';
        }
      }
      function _shortText(s, maxLen) { const n = Number.isFinite(maxLen) ? maxLen : 80; const t = String(s || "").replace(/\s+/g, " ").trim(); if (!t) return ""; return t.length > n ? (t.slice(0, n) + "...") : t; }
      function _coerceInt(v, fallback) { const n = parseInt(String(v != null ? v : ""), 10); return Number.isFinite(n) ? n : fallback; }
      function _normalizeVocalsFlag(v) { if (v === true) return true; if (v === false) return false; return Boolean(v); }
      function _tryParseJsonObject(v) { if (v && typeof v === "object" && !Array.isArray(v)) return v; if (typeof v === "string" && v.trim()) { try { const parsed = JSON.parse(v); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed; } catch {} } return null; }
      function _restoreCompositionPlanFromObject(plan) {
        if (!plan || typeof plan !== "object") return false;
        const pos = Array.isArray(plan.positive_global_styles) ? plan.positive_global_styles.filter(Boolean) : [];
        const neg = Array.isArray(plan.negative_global_styles) ? plan.negative_global_styles.filter(Boolean) : [];
        const sections = Array.isArray(plan.sections) ? plan.sections : [];
        cpState = { positive_global_styles: [...pos], negative_global_styles: [...neg], sections: sections.map(s => { const localStyles = Array.isArray(s && s.local_styles) ? (s.local_styles || []).filter(Boolean) : []; const durationMs = (typeof (s && s.duration_ms) === "number" && s.duration_ms > 0) ? s.duration_ms : null; const lyrics = (typeof (s && s.lyrics) === "string") ? s.lyrics : ""; return { local_styles: [...localStyles], duration_ms: durationMs, lyrics }; }), bpm: (typeof plan.bpm === "number" && plan.bpm > 0) ? plan.bpm : null, key: (typeof plan.key === "string") ? plan.key : null };
        const bpmEl = document.getElementById("cpBpm"); const keyEl = document.getElementById("cpKey"); if (bpmEl) bpmEl.value = cpState.bpm ? String(cpState.bpm) : ""; if (keyEl) keyEl.value = cpState.key ? String(cpState.key) : "";
        renderTags("positiveStyles", cpState.positive_global_styles, "removePositiveStyle"); renderTags("negativeStyles", cpState.negative_global_styles, "removeNegativeStyle"); renderSections(); return true;
      }
      function restoreJobParams(job) {
        const j = job || {}; const params = (j.params && typeof j.params === "object") ? j.params : {}; const providerId = String(j.provider || params.provider || "").trim(); const providerParams = (params.provider_params && typeof params.provider_params === "object") ? params.provider_params : {};
        const basePrompt = (typeof params.base_prompt === "string") ? params.base_prompt : (typeof j.prompt === "string" ? j.prompt : "");
        const lyrics = (typeof params.lyrics === "string") ? params.lyrics : "";
        const durationSec = _coerceInt(params.duration_sec, 45);
        const vocals = _normalizeVocalsFlag(params.vocals);
        const seed = (typeof params.seed === "number") ? params.seed : null;
        const lines = ["将用该生成记录的参数覆盖当前表单设置：", "- provider: " + (providerId || "(unknown)"), "- duration_sec: " + durationSec, "- vocals: " + (vocals ? "on" : "off"), "- seed: " + (seed === null ? "(null)" : seed), "- prompt: " + (_shortText(basePrompt, 80) || "(empty)"), "- lyrics: " + (lyrics ? "有" : "无"), "", "继续恢复？"];
        const ok = window.confirm(lines.join("\n")); if (!ok) return;
        // If the record was generated in an audio-edit task_type, switch UI to remix mode
        // so restored provider_params (task_type + upload ids etc) remain visible.
        const restoredTaskType = String((providerParams && providerParams.task_type) || "").trim();
        const isEdit = ["cover", "repaint", "lego", "extract", "complete"].includes(restoredTaskType);
        if (isEdit) {
          if (creationMode !== "remix") setCreationMode("remix");
          const map = { cover: "style-transfer", repaint: "section-edit", lego: "section-edit", extract: "audio-process", complete: "audio-process" };
          const sub = map[restoredTaskType] || "style-transfer";
          if (creationSubMode !== sub) setCreationSubMode(sub);
        } else {
          if (creationMode !== "original") setCreationMode("original");
          // Preserve current original simple/advanced subtab, but ensure provider fields render.
          if (creationSubMode !== "simple" && creationSubMode !== "advanced") setCreationSubMode("simple");
        }
        renderProviderFields({ reset: true });
        if (durationSlider) { const clamped = Math.max(3, Math.min(600, durationSec)); durationSlider.value = String(clamped); durationValue.textContent = String(clamped) + " 秒"; }
        if (durationMobileSlider && durationMobileValue) { const clamped = Math.max(3, Math.min(600, durationSec)); durationMobileSlider.value = String(clamped); durationMobileValue.textContent = String(clamped) + " 秒"; }
        const vocalsEl = document.getElementById("vocals"); if (vocalsEl && !vocalsEl.disabled) vocalsEl.value = vocals ? "on" : "off";
        if (vocalsMobileEl && !vocalsMobileEl.disabled) vocalsMobileEl.value = vocals ? "on" : "off";
        const seedEl = document.getElementById("seed"); if (seedEl) seedEl.value = (seed === null || seed === undefined) ? "" : String(seed);
        if (seedMobileEl) seedMobileEl.value = (seed === null || seed === undefined) ? "" : String(seed);
        if (promptEl) promptEl.value = basePrompt || "";
        if (promptMobileEl) promptMobileEl.value = basePrompt || "";
        if (lyricsEl) lyricsEl.value = lyrics || "";
        if (lyricsMobileEl) lyricsMobileEl.value = lyrics || "";
        updateLyricsUi();
        const meta = getProviderMeta(getSelectedProviderId()); const normalizedProviderParams = { ...(providerParams || {}) };
        if (normalizedProviderParams.output_format == null && params.output_format != null) { normalizedProviderParams.output_format = params.output_format; }
        if (meta && Array.isArray(meta.fields) && meta.fields.length > 0) {
          for (const field of meta.fields) {
            const el = providerFieldsEl.querySelector("[data-key=\"" + field.key + "\"]");
            if (!el) continue;
            const v = normalizedProviderParams[field.key];
            if (el.tagName === "INPUT" && el.type === "checkbox") { el.checked = toBool(v); continue; }
            if (field.kind === "json") {
              if (v === null || v === undefined || v === "") el.value = "";
              else if (typeof v === "string") el.value = v;
              else { try { el.value = JSON.stringify(v, null, 2); } catch { el.value = String(v); } }
              continue;
            }
            el.value = (v === null || v === undefined) ? "" : String(v);
          }
          renderProviderFields();
        }
        setStatus("已恢复参数（来自生成记录）", "ok");
      }
      function renderList(jobs, opts) {
        const incremental = opts && opts.incremental;
        const targetList = _pickContainer(list2El, listEl);
        if (!targetList) return;
        if (!jobs || jobs.length === 0) { if (!incremental) targetList.innerHTML = ""; return; }
        if (incremental) {
          const existingIds = new Set(); for (const child of targetList.children) { if (child.dataset && child.dataset.jobId) existingIds.add(child.dataset.jobId); }
          for (const base of jobs) { const j = (base && base.job_id && liveJobsById.has(base.job_id)) ? liveJobsById.get(base.job_id) : base; if (!j || !j.job_id || existingIds.has(j.job_id)) { if (j && j.job_id) { const existingRow = targetList.querySelector("[data-job-id=\"" + j.job_id + "\"]"); if (existingRow) { const statusEl = existingRow.querySelector(".job-status"); if (statusEl) { statusEl.textContent = _statusLabel(j.status, j.queue_position, j.queue_depth); statusEl.className = "job-status " + j.status; } const oldStatus = existingRow.dataset.status; if (oldStatus !== j.status) { const newRow = _buildJobRow(j); if (newRow) existingRow.replaceWith(newRow); continue; } if (j.audio_url && !existingRow.querySelector("audio")) { const a = document.createElement("audio"); a.controls = true; a.preload = "metadata"; attachAuthenticatedAudio(a, j.audio_url); existingRow.appendChild(a); } } } continue; } const row = _buildJobRow(j); if (row) targetList.insertBefore(row, targetList.firstChild); }
          return;
        }
        targetList.innerHTML = "";
        for (const base of jobs) { const j = (base && base.job_id && liveJobsById.has(base.job_id)) ? liveJobsById.get(base.job_id) : base; const row = _buildJobRow(j); if (row) targetList.appendChild(row); }
      }
      function _statusLabel(status, queuePosition, queueDepth) { const map = { queued: "排队中", running: "生成中", succeeded: "已完成", failed: "失败" }; let label = map[status] || status; if (status === "queued") { if (queuePosition && queuePosition > 0) { label = "排队中（第" + queuePosition + "位/共" + (queueDepth || "?") + "位）"; } else if (queueDepth && queueDepth > 0) { label = "排队中（共" + queueDepth + "位）"; } } return label; }
      function _buildJobRow(j) {
        if (!j || !j.job_id) return null;
        const row = document.createElement("div"); row.className = "history-item"; row.dataset.jobId = j.job_id; row.dataset.status = j.status;
        const line1 = document.createElement("div"); line1.className = "history-item-line1";
        const promptSpan = document.createElement("span"); promptSpan.className = "history-item-prompt"; const _meta = j.metadata || {}; const _title = _meta.title || j.prompt || "未命名作品"; const _sub = _meta.author ? (" · " + _meta.author) : ""; promptSpan.textContent = _shortText(_title + _sub, 80); line1.appendChild(promptSpan);
        const statusBadge = document.createElement("span"); statusBadge.className = "job-status " + j.status; statusBadge.textContent = _statusLabel(j.status, j.queue_position, j.queue_depth); line1.appendChild(statusBadge);
        row.appendChild(line1);
        const line2 = document.createElement("div"); line2.className = "history-item-line2";
        const meta = document.createElement("div"); meta.className = "history-item-meta";
        const providerTag = document.createElement("span"); providerTag.textContent = j.provider || ""; meta.appendChild(providerTag);
        if (j.duration_sec) { const dur = document.createElement("span"); dur.textContent = Math.round(j.duration_sec) + "秒"; meta.appendChild(dur); }
        line2.appendChild(meta);
        const actions = document.createElement("div"); actions.className = "history-item-actions";
        const restoreBtn = document.createElement("button"); restoreBtn.className = "btn btn-secondary btn-sm"; restoreBtn.innerHTML = '<svg class="icon icon-sm" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>'; restoreBtn.title = "恢复参数"; restoreBtn.addEventListener("click", (e) => { e.stopPropagation(); restoreJobParams(j); });
        const deleteBtn = document.createElement("button"); deleteBtn.className = "btn-danger btn-sm"; deleteBtn.innerHTML = '<svg class="icon icon-sm" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'; deleteBtn.title = "删除"; deleteBtn.addEventListener("click", async (e) => { e.stopPropagation(); if (!window.confirm("确定删除记录？")) return; try { await fetchJson("/api/jobs/" + j.job_id, { method: "DELETE" }); if (currentJobId === j.job_id) { player.removeAttribute("src"); player.load(); downloadLink.style.display = "none"; extendGroup.style.display = "none"; currentJobId = null; } await loadHistoryPage(historyOffset); } catch (err) { setError("删除失败：" + errorMessage(err)); } });
        actions.appendChild(restoreBtn);
        if (j.status === "queued") { const cancelBtn = document.createElement("button"); cancelBtn.className = "btn btn-secondary btn-sm"; cancelBtn.textContent = "取消"; cancelBtn.title = "取消排队"; cancelBtn.addEventListener("click", async (e) => { e.stopPropagation(); if (!window.confirm("确定取消排队？")) return; try { await fetchJson("/api/jobs/" + j.job_id + "/cancel", { method: "POST" }); await loadHistoryPage(historyOffset); } catch (err) { setError("取消排队失败：" + errorMessage(err)); } }); actions.appendChild(cancelBtn); }
        if (j.status === "succeeded") { const editMetaBtn = document.createElement("button"); editMetaBtn.className = "btn btn-secondary btn-sm"; editMetaBtn.innerHTML = '<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>'; editMetaBtn.title = "编辑信息"; editMetaBtn.addEventListener("click", (e) => { e.stopPropagation(); showEditMetadata(j); }); actions.appendChild(editMetaBtn); const shareWrap = document.createElement("span"); shareWrap.className = "share-control"; if (j.visibility === "published") { const unpublishBtn = document.createElement("button"); unpublishBtn.className = "btn btn-secondary btn-sm"; unpublishBtn.textContent = "取消发布"; unpublishBtn.addEventListener("click", async (e) => { e.stopPropagation(); try { await fetchJson("/api/jobs/" + j.job_id + "/unpublish", { method: "POST" }); await loadHistoryPage(historyOffset); loadCommunity().catch(() => {}); } catch (err) { setError("取消发布失败：" + errorMessage(err)); } }); shareWrap.appendChild(unpublishBtn); } else { const permSelect = document.createElement("select"); permSelect.innerHTML = '<option value="listen_only">仅试听</option><option value="downloadable">可下载</option>'; const publishBtn = document.createElement("button"); publishBtn.className = "btn btn-secondary btn-sm"; publishBtn.textContent = "发布"; publishBtn.addEventListener("click", async (e) => { e.stopPropagation(); try { await fetchJson("/api/jobs/" + j.job_id + "/publish", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ share_permission: permSelect.value }) }); await loadHistoryPage(historyOffset); loadCommunity().catch(() => {}); } catch (err) { setError("发布失败：" + errorMessage(err)); } }); shareWrap.appendChild(permSelect); shareWrap.appendChild(publishBtn); } actions.appendChild(shareWrap); }
        actions.appendChild(deleteBtn);
        line2.appendChild(actions);
        row.appendChild(line2);
        if (j.audio_url) { const a = document.createElement("audio"); a.controls = true; a.preload = "metadata"; attachAuthenticatedAudio(a, j.audio_url); row.appendChild(a); }
        row.addEventListener("click", () => { currentJobId = j.job_id; jobIdEl.textContent = currentJobId; setError(""); if (j.audio_url) { setMainPlayerAudio(j); } else { setMainPlayerAudio(null); } });
        return row;
      }
      async function startGenerate() {
        const btn = document.getElementById("generateBtn"); if (btn.disabled) return; setError(""); const count = parseInt(document.getElementById("count").value, 10);
        setStatus(count > 1 ? "提交 " + count + " 首候选任务中..." : "提交任务中..."); downloadLink.style.display = "none"; refreshBtn.style.display = "none"; extendGroup.style.display = "none"; player.removeAttribute("src"); player.load();
        btn.disabled = true; btn.innerHTML = '<svg class="icon icon-sm" viewBox="0 0 24 24" style="animation: spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 生成中...'; if (generateBtnMobile) { generateBtnMobile.disabled = true; generateBtnMobile.textContent = "生成中..."; }
        const prompt = document.getElementById("prompt").value.trim(); const lyrics = getLyricsPayloadValue(); const duration = parseInt(document.getElementById("duration").value, 10); const vocals = document.getElementById("vocals").value === "on"; const seedRaw = document.getElementById("seed").value.trim(); const providerId = getSelectedProviderId();
        const payload = { prompt, lyrics: lyrics, duration_sec: duration, vocals, seed: seedRaw ? parseInt(seedRaw, 10) : null, provider: providerId || null, provider_params: collectProviderParams() };
        if (!_validateGenerateCommon(payload)) { btn.disabled = false; _updateGenerateBtnLabel(); return; }
        if (count > 1) { payload.count = count; const data = await fetchJson("/api/generate_many", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); const newIds = data.job_ids || []; currentJobs = newIds; currentJobId = newIds[0] || null; if (data.quota && currentUser) { currentUser.quota = data.quota; updateQuotaDisplay(currentUser); } } else { const data = await fetchJson("/api/generate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); currentJobId = data.job_id; currentJobs = [currentJobId]; if (data.quota && currentUser) { currentUser.quota = data.quota; updateQuotaDisplay(currentUser); } }
        jobIdEl.textContent = currentJobId || "-"; refreshBtn.style.display = "inline-flex"; setStatus("已提交，生成中..."); loadHistoryPage(0).catch(() => {});
        startJobPolling(); await refreshJobs(currentJobs);
      }
      async function refreshJobs(jobIds, opts) {
        try { if (!jobIds || jobIds.length === 0) return; const updateStatus = !(opts && opts.updateStatus === false); const data = await fetchJson("/api/jobs?ids=" + jobIds.join(",")); const jobs = (data.jobs || []); for (const j of jobs) { if (j && j.job_id) liveJobsById.set(j.job_id, j); } renderList((historyJobs && historyJobs.length > 0) ? historyJobs : jobs, { incremental: true });
        const current = jobs.find(j => j.job_id === currentJobId) || jobs[0]; if (current) { currentJobId = current.job_id; currentJobSongId = current.song_id || null; currentJobProvider = current.provider || null; jobIdEl.textContent = currentJobId; }
        const anyRunning = jobs.some(j => j.status === "running"); const anyQueued = jobs.some(j => j.status === "queued"); const anyActive = anyRunning || anyQueued; const anyFailed = jobs.some(j => j.status === "failed"); const anySucceeded = jobs.some(j => j.status === "succeeded");
        if (updateStatus) { if (anyQueued && !anyRunning) { const queuedJobs = jobs.filter(j => j.status === "queued"); const queueInfo = queuedJobs.length > 0 ? "（" + queuedJobs.length + "个排队中）" : ""; setStatus("排队中..." + queueInfo); } else if (anyRunning) { const queuedCount = jobs.filter(j => j.status === "queued").length; const queueInfo = queuedCount > 0 ? " + " + queuedCount + "个排队" : ""; setStatus("生成中..." + queueInfo); } if (!anyActive && anySucceeded) setStatus("生成完成", "ok"); if (!anyActive && !anySucceeded && anyFailed) setStatus("生成失败", "err"); }
        if (!anyActive && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        if (!anyActive) { const btn = document.getElementById("generateBtn"); btn.disabled = false; _updateGenerateBtnLabel(); }
        if (!anyActive && updateStatus) { setTimeout(async () => { await loadHistoryPage(0); renderList(historyJobs || [], { incremental: true }); }, 300); }
        if (current && current.audio_url) { setMainPlayerAudio(current); } else { downloadLink.style.display = "none"; extendGroup.style.display = "none"; }
        if (updateStatus && jobs.length === 1 && jobs[0].status === "failed") { setError(jobs[0].error || "未知错误"); }
        } catch (e) { setError(errorMessage(e)); }
      }
      async function extendCurrent() { setError(""); if (!currentJobId) { setError("没有可延长的 Job。"); return; } const extra = parseInt(document.getElementById("extendSec").value, 10); if (!Number.isFinite(extra) || extra < 3 || extra > 180) { setError("延长秒数建议 3–180。"); return; } setStatus("提交延长任务中..."); const data = await fetchJson("/api/extend", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ job_id: currentJobId, extra_sec: extra, provider: getSelectedProviderId() || null, provider_params: collectProviderParams() }) }); const newJobId = data.job_id; currentJobs = [newJobId]; currentJobId = newJobId; if (data.quota && currentUser) { currentUser.quota = data.quota; updateQuotaDisplay(currentUser); } jobIdEl.textContent = newJobId; refreshBtn.style.display = "inline-flex"; extendGroup.style.display = "none"; loadHistoryPage(0).catch(() => {}); startJobPolling(); await refreshJobs(currentJobs); }
      async function fetchRandomSample() { try { const data = await fetchJson("/api/random_sample"); return data; } catch (e) { console.error("Failed to fetch random sample:", e); return null; } }
      async function fillRandomPrompt() {
        const sample = await fetchRandomSample();
        if (sample && sample.prompt) {
          promptEl.value = sample.prompt;
          if (promptMobileEl) promptMobileEl.value = sample.prompt;
          setStatus("已随机填充描述", "ok");
        }
      }
      async function fillRandomLyrics() {
        const sample = await fetchRandomSample();
        if (sample && sample.lyrics) {
          if (lyricsEl) lyricsEl.value = sample.lyrics;
          if (lyricsMobileEl) lyricsMobileEl.value = sample.lyrics;
          setStatus("已随机填充歌词", "ok");
        }
      }
      async function fillRandomAll() {
        const sample = await fetchRandomSample();
        if (!sample) { setError("获取随机样本失败"); return; }
        if (sample.prompt) {
          promptEl.value = sample.prompt;
          if (promptMobileEl) promptMobileEl.value = sample.prompt;
        }
        if (sample.lyrics) {
          if (lyricsEl) lyricsEl.value = sample.lyrics;
          if (lyricsMobileEl) lyricsMobileEl.value = sample.lyrics;
        }
        if (sample.duration) {
          const clamped = Math.max(3, Math.min(600, sample.duration));
          if (durationSlider && durationValue) { durationSlider.value = String(clamped); durationValue.textContent = String(clamped) + " 秒"; }
          if (durationMobileSlider && durationMobileValue) { durationMobileSlider.value = String(clamped); durationMobileValue.textContent = String(clamped) + " 秒"; }
        }
        setStatus("已随机填充", "ok");
      }
      function updateRandomButtonsVisibility() {
        const showRandomButtons = true;
        const randomPromptBtn = document.getElementById("randomPromptBtn");
        const randomLyricsBtn = document.getElementById("randomLyricsBtn");
        const randomFillAllBtn = document.getElementById("randomFillAllBtn");
        const randomFillAllBtnMobile = document.getElementById("randomFillAllBtnMobile");
        if (randomPromptBtn) randomPromptBtn.style.display = showRandomButtons ? "inline-flex" : "none";
        if (randomLyricsBtn) randomLyricsBtn.style.display = showRandomButtons ? "inline-flex" : "none";
        if (randomFillAllBtn) randomFillAllBtn.style.display = showRandomButtons ? "inline-flex" : "none";
        if (randomFillAllBtnMobile) randomFillAllBtnMobile.style.display = showRandomButtons ? "inline-flex" : "none";
      }
      function _updateGenerateBtnLabel() { const count = parseInt(document.getElementById("count").value, 10); const btn = document.getElementById("generateBtn"); btn.innerHTML = count > 1 ? icon("sparkles", "icon-sm") + " 创作 " + count + " 首" : icon("sparkles", "icon-sm") + " 开始创作"; if (generateBtnMobile) { generateBtnMobile.disabled = btn.disabled; generateBtnMobile.textContent = count > 1 ? "创作 " + count + " 首" : "开始创作"; } }
      document.getElementById("generateBtn").addEventListener("click", () => { startGenerate().catch(e => { setError(errorMessage(e)); setStatus(""); const btn = document.getElementById("generateBtn"); btn.disabled = false; _updateGenerateBtnLabel(); }); });
      document.getElementById("count").addEventListener("change", _updateGenerateBtnLabel);
      _updateGenerateBtnLabel();
      const randomPromptBtnEl = document.getElementById("randomPromptBtn"); const randomLyricsBtnEl = document.getElementById("randomLyricsBtn"); const randomFillAllBtnEl = document.getElementById("randomFillAllBtn");
      if (randomPromptBtnEl) { randomPromptBtnEl.addEventListener("click", () => { fillRandomPrompt().catch(e => console.error("fillRandomPrompt error:", e)); }); }
      if (randomLyricsBtnEl) { randomLyricsBtnEl.addEventListener("click", () => { fillRandomLyrics().catch(e => console.error("fillRandomLyrics error:", e)); }); }
      if (randomFillAllBtnEl) { randomFillAllBtnEl.addEventListener("click", () => { fillRandomAll().catch(e => console.error("fillRandomAll error:", e)); }); }
      const randomFillAllBtnMobileEl = document.getElementById("randomFillAllBtnMobile");
      if (randomFillAllBtnMobileEl) { randomFillAllBtnMobileEl.addEventListener("click", () => { fillRandomAll().catch(e => console.error("fillRandomAll(mobile) error:", e)); }); }

      function _bindButtonLike(el, fn) {
        if (!el) return;
        el.addEventListener("click", (e) => { e.preventDefault(); fn(); });
        el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } });
      }
      document.querySelectorAll("[data-clear-audio]").forEach(el => {
        const which = String(el.dataset.clearAudio || "").trim();
        if (!which) return;
        _bindButtonLike(el, () => { try { clearAudioInput(which); } catch {} });
      });
      document.querySelectorAll("[data-cp-genre]").forEach(btn => {
        const preset = String(btn.dataset.cpGenre || "").trim();
        if (!preset) return;
        btn.addEventListener("click", (e) => { e.preventDefault(); applyGenrePreset(preset); });
      });
      document.querySelectorAll("[data-cp-clear]").forEach(btn => {
        btn.addEventListener("click", (e) => { e.preventDefault(); clearCompositionPlan(); });
      });
      document.querySelectorAll("[data-cp-add-style]").forEach(btn => {
        const which = String(btn.dataset.cpAddStyle || "").trim();
        btn.addEventListener("click", (e) => { e.preventDefault(); if (which === "negative") addNegativeStyle(); else addPositiveStyle(); });
      });
      document.querySelectorAll("[data-cp-add-section]").forEach(btn => {
        const kind = String(btn.dataset.cpAddSection || "").trim();
        btn.addEventListener("click", (e) => { e.preventDefault(); if (kind && kind !== "custom") addSection(kind); else addSection(); });
      });
      advancedEl.addEventListener("change", () => renderProviderFields());
      if (srcAudioInput) { srcAudioInput.addEventListener("change", function() { if (this.files && this.files[0]) handleAudioFileInput("src", this.files[0]); }); }
      if (refAudioInput) { refAudioInput.addEventListener("change", function() { if (this.files && this.files[0]) handleAudioFileInput("ref", this.files[0]); }); }
      if (srcAudioInputMobile) { srcAudioInputMobile.addEventListener("change", function() { if (this.files && this.files[0]) handleAudioFileInput("src", this.files[0]); }); }
      if (refAudioInputMobile) { refAudioInputMobile.addEventListener("change", function() { if (this.files && this.files[0]) handleAudioFileInput("ref", this.files[0]); }); }
      historyLimit = loadHistoryPageSizePref();
      if (historyPageSizeEl) { historyPageSizeEl.value = String(historyLimit); historyPageSizeEl.addEventListener("change", () => { const n = parseInt(String(historyPageSizeEl.value || "20"), 10); historyLimit = (Number.isFinite(n) && n > 0) ? n : 20; saveHistoryPageSizePref(); loadHistoryPage(0).catch(e => setError(errorMessage(e))); }); }
      if (historyPageSizeEl2) { historyPageSizeEl2.value = String(historyLimit); historyPageSizeEl2.addEventListener("change", () => { const n = parseInt(String(historyPageSizeEl2.value || "20"), 10); historyLimit = (Number.isFinite(n) && n > 0) ? n : 20; saveHistoryPageSizePref(); loadHistoryPage(0).catch(e => setError(errorMessage(e))); }); }
      if (historyPrevBtn) { historyPrevBtn.addEventListener("click", () => { const nextOffset = Math.max(0, historyOffset - historyLimit); loadHistoryPage(nextOffset).catch(e => setError(errorMessage(e))); }); }
      if (historyNextBtn) { historyNextBtn.addEventListener("click", () => { const nextOffset = historyOffset + historyLimit; if (nextOffset >= historyTotal) return; loadHistoryPage(nextOffset).catch(e => setError(errorMessage(e))); }); }
      if (historyPrevBtn2) { historyPrevBtn2.addEventListener("click", () => { const nextOffset = Math.max(0, historyOffset - historyLimit); loadHistoryPage(nextOffset).catch(e => setError(errorMessage(e))); }); }
      if (historyNextBtn2) { historyNextBtn2.addEventListener("click", () => { const nextOffset = historyOffset + historyLimit; if (nextOffset >= historyTotal) return; loadHistoryPage(nextOffset).catch(e => setError(errorMessage(e))); }); }
      updateHistoryPagerUi();
      const clearAllBtnEl = document.getElementById("clearAllBtn");
      if (clearAllBtnEl) { clearAllBtnEl.addEventListener("click", async () => { if (!window.confirm("确定清空所有生成记录？此操作不可恢复。")) return; try { await fetchJson("/api/jobs", { method: "DELETE" }); listEl.innerHTML = ""; list2El.innerHTML = ""; player.removeAttribute("src"); player.load(); downloadLink.style.display = "none"; extendGroup.style.display = "none"; currentJobId = null; currentJobs = []; setStatus("已清空", "ok"); loadHistoryPage(0).catch(() => {}); } catch (err) { setError("清空失败：" + errorMessage(err)); } }); }
      _decorateStaticBadges(); _updatePromptBadge();
      if (cpEditorEl) { ["input", "change", "click", "keyup"].forEach(evt => { cpEditorEl.addEventListener(evt, () => _updatePromptBadge()); }); }
      const loginForm = document.getElementById("loginPanel");
      if (loginForm) {
        loginForm.addEventListener("submit", (e) => {
          e.preventDefault();
          if (_isRegisterModeNow()) return;
          login().catch(err => setAuthError(errorMessage(err)));
        });
      }
      const registerForm = document.getElementById("registerPanel");
      if (registerForm) {
        registerForm.addEventListener("submit", (e) => {
          e.preventDefault();
          if (!_isRegisterModeNow()) return;
          const inviteEl = document.getElementById("registerInvite");
          const invite = inviteEl ? String(inviteEl.value || "").trim() : "";
          if (!invite && inviteEl) { inviteEl.focus(); setAuthError("请先填写邀请码。"); return; }
          registerAccount().catch(err => setAuthError(errorMessage(err)));
        });
      }
      const loginUsernameEl = document.getElementById("loginUsername");
      const loginPasswordEl = document.getElementById("loginPassword");
      const registerUsernameEl = document.getElementById("registerUsername");
      const registerPasswordEl = document.getElementById("registerPassword");
      const registerInviteEl = document.getElementById("registerInvite");
      if (loginUsernameEl && loginPasswordEl) {
        loginUsernameEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); loginPasswordEl.focus(); } });
      }
      // For mobile keyboards, rely on <form submit> rather than keydown Enter (more reliable on iOS/Android).
      if (registerUsernameEl && registerPasswordEl) {
        registerUsernameEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); registerPasswordEl.focus(); } });
      }
      if (registerPasswordEl && registerInviteEl) {
        registerPasswordEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); registerInviteEl.focus(); } });
      }
      // For mobile keyboards, rely on <form submit> rather than keydown Enter.
      showLoginBtn.addEventListener("click", () => showAuthMode("login"));
      showRegisterBtn.addEventListener("click", () => showAuthMode("register"));
      const showAuthBtnEl = document.getElementById("showAuthBtn");
      if (showAuthBtnEl) { showAuthBtnEl.addEventListener("click", () => { showAuthMode(registerPanel.classList.contains("hidden") ? "register" : "login"); }); }

      const toggleLoginPasswordBtn = document.getElementById("toggleLoginPassword");
      if (toggleLoginPasswordBtn && loginPasswordEl) {
        toggleLoginPasswordBtn.addEventListener("click", () => {
          const isHidden = loginPasswordEl.type === "password";
          loginPasswordEl.type = isHidden ? "text" : "password";
          toggleLoginPasswordBtn.textContent = isHidden ? "隐藏" : "查看";
        });
      }
      const toggleRegisterPasswordBtn = document.getElementById("toggleRegisterPassword");
      if (toggleRegisterPasswordBtn && registerPasswordEl) {
        toggleRegisterPasswordBtn.addEventListener("click", () => {
          const isHidden = registerPasswordEl.type === "password";
          registerPasswordEl.type = isHidden ? "text" : "password";
          toggleRegisterPasswordBtn.textContent = isHidden ? "隐藏" : "查看";
        });
      }

      const clearPromptBtnEl = document.getElementById("clearPromptBtn");
      if (clearPromptBtnEl) {
        clearPromptBtnEl.addEventListener("click", () => {
          if (promptEl) promptEl.value = "";
          document.querySelectorAll("#quickGenreTags .tag").forEach(t => t.classList.remove("active"));
          setStatus("已清空描述", "ok");
        });
      }
      const clearPromptBtnMobileEl = document.getElementById("clearPromptBtnMobile");
      if (clearPromptBtnMobileEl) {
        clearPromptBtnMobileEl.addEventListener("click", () => {
          if (promptMobileEl) promptMobileEl.value = "";
          if (promptEl) promptEl.value = "";
          const quickGenreTagsMobileEl = document.getElementById("quickGenreTagsMobile");
          if (quickGenreTagsMobileEl) quickGenreTagsMobileEl.querySelectorAll(".tag").forEach(t => t.classList.remove("active"));
          document.querySelectorAll("#quickGenreTags .tag").forEach(t => t.classList.remove("active"));
          setStatus("已清空描述", "ok");
        });
      }
      document.getElementById("logoutBtn").addEventListener("click", () => { setSession("", null); stopEventStream(); providersMeta = null; historyJobs = []; listEl.innerHTML = ""; list2El.innerHTML = ""; revokeAudioBlobUrls(); setMainPlayerAudio(null); });
      const logoutBtnMobile = document.getElementById("logoutBtnMobile");
      if (logoutBtnMobile) { logoutBtnMobile.addEventListener("click", () => { setSession("", null); stopEventStream(); providersMeta = null; historyJobs = []; listEl.innerHTML = ""; list2El.innerHTML = ""; revokeAudioBlobUrls(); setMainPlayerAudio(null); }); }
      document.getElementById("fcpSubmitBtn").addEventListener("click", () => submitForceChangePwd().catch(e => { document.getElementById("fcpError").textContent = errorMessage(e); document.getElementById("fcpError").style.display = "block"; }));
      document.getElementById("metaSaveBtn").addEventListener("click", () => saveEditMetadata().catch(e => { document.getElementById("metaError").textContent = errorMessage(e); document.getElementById("metaError").style.display = "block"; }));
      document.getElementById("metaCancelBtn").addEventListener("click", () => hideEditMetadata());
      document.getElementById("songInfoCloseBtn").addEventListener("click", () => hideSongInfo());
      navCreate.addEventListener("click", (e) => { e.preventDefault(); showView("create"); });
      navDiscover.addEventListener("click", (e) => { e.preventDefault(); showView("discover"); });
      document.getElementById("refreshCommunityBtn").addEventListener("click", () => { loadCommunity().catch(e => setError(errorMessage(e))); });
      refreshCurrentUser();
      refreshBtn.addEventListener("click", () => { if (!currentJobs || currentJobs.length === 0) return; refreshJobs(currentJobs).catch(e => setError(errorMessage(e))); });
      extendBtn.addEventListener("click", () => { extendCurrent().catch(e => setError(errorMessage(e))); });
      document.getElementById("positiveStyleInput").addEventListener("keypress", (e) => { if (e.key === "Enter") { e.preventDefault(); addPositiveStyle(); } });
      document.getElementById("negativeStyleInput").addEventListener("keypress", (e) => { if (e.key === "Enter") { e.preventDefault(); addNegativeStyle(); } });
      document.querySelectorAll(".mode-tab").forEach(btn => { btn.addEventListener("click", () => setCreationMode(btn.dataset.mode)); });
      document.querySelectorAll("#subTabOriginal .sub-tab").forEach(btn => { btn.addEventListener("click", () => setCreationSubMode(btn.dataset.sub)); });
      document.querySelectorAll("#subTabRemix .sub-tab").forEach(btn => { btn.addEventListener("click", () => setCreationSubMode(btn.dataset.sub)); });
      document.querySelectorAll("#subTabOriginalMobile .sub-tab").forEach(btn => { btn.addEventListener("click", () => setCreationSubMode(btn.dataset.sub)); });
      document.querySelectorAll("#subTabRemixMobile .sub-tab").forEach(btn => { btn.addEventListener("click", () => setCreationSubMode(btn.dataset.sub)); });
      document.querySelectorAll("#mobileTabBar .tab-item").forEach(btn => { btn.addEventListener("click", () => showMobileTab(btn.dataset.tab)); });

      // --- Viewport resize: re-render lists into correct container ---
      let _lastDesktop = _isDesktopViewport();
      window.addEventListener("resize", () => {
        const nowDesktop = _isDesktopViewport();
        if (nowDesktop === _lastDesktop) return;
        _lastDesktop = nowDesktop;
        // Keep the correct layout visible when crossing the breakpoint.
        try {
          const loggedIn = localMode || Boolean(currentUser && authToken);
          const mobilePanelsEl = document.getElementById("mobilePanels");
          if (pcLayout) pcLayout.style.display = (loggedIn && nowDesktop) ? "" : "none";
          if (mobilePanelsEl) mobilePanelsEl.style.display = (loggedIn && !nowDesktop) ? "" : "none";
          if (mobileTabBar) mobileTabBar.style.display = (loggedIn && !nowDesktop) ? "" : "none";
        } catch {}
        if (historyJobs && historyJobs.length > 0) renderList(historyJobs, { incremental: false });
        loadCommunity().catch(() => {});
      });

      // --- Mobile form wiring ---
      function _syncMobileFormToDesktop() {
        if (promptMobileEl) promptEl.value = promptMobileEl.value;
        if (durationMobileSlider) { durationSlider.value = durationMobileSlider.value; durationValue.textContent = durationMobileSlider.value + " 秒"; }
        if (lyricsMobileEl && lyricsEl) lyricsEl.value = lyricsMobileEl.value;
        if (vocalsMobileEl) document.getElementById("vocals").value = vocalsMobileEl.value;
        if (seedMobileEl) document.getElementById("seed").value = seedMobileEl.value;
        if (countMobileEl) document.getElementById("count").value = countMobileEl.value;
        if (providerFieldsMobileEl && providerFieldsEl) {
          providerFieldsMobileEl.querySelectorAll("[data-key]").forEach(mEl => {
            const dEl = providerFieldsEl.querySelector("[data-key=\"" + mEl.dataset.key + "\"]");
            if (!dEl) return;
            if (mEl.type === "checkbox") dEl.checked = mEl.checked;
            else dEl.value = mEl.value;
          });
        }
      }
      if (generateBtnMobile) {
        generateBtnMobile.addEventListener("click", () => {
          _syncMobileFormToDesktop();
          startGenerate().catch(e => { setError(errorMessage(e)); setStatus(""); if (generateBtnMobile) { generateBtnMobile.disabled = false; generateBtnMobile.textContent = "开始创作"; } });
        });
      }
      if (durationMobileSlider && durationMobileValue) {
        durationMobileSlider.addEventListener("input", () => { durationMobileValue.textContent = durationMobileSlider.value + " 秒"; });
      }
      // Mobile original simple/advanced mode is driven by the sub-tabs (creationSubMode).
      const quickGenreTagsMobileEl = document.getElementById("quickGenreTagsMobile");
      if (quickGenreTagsMobileEl) {
        quickGenreTagsMobileEl.addEventListener("click", (e) => { const tag = e.target.closest(".tag"); if (tag && promptMobileEl) { const genre = tag.dataset.genre; if (promptMobileEl.value.trim()) { promptMobileEl.value = promptMobileEl.value.trim() + "，" + genre; } else { promptMobileEl.value = genre; } quickGenreTagsMobileEl.querySelectorAll(".tag").forEach(t => t.classList.remove("active")); tag.classList.add("active"); setTimeout(() => tag.classList.remove("active"), 500); } });
      }
      const clearAllBtnMobileEl = document.getElementById("clearAllBtnMobile");
      if (clearAllBtnMobileEl) { clearAllBtnMobileEl.addEventListener("click", async () => { if (!window.confirm("确定清空所有生成记录？此操作不可恢复。")) return; try { await fetchJson("/api/jobs", { method: "DELETE" }); listEl.innerHTML = ""; list2El.innerHTML = ""; player.removeAttribute("src"); player.load(); downloadLink.style.display = "none"; extendGroup.style.display = "none"; currentJobId = null; currentJobs = []; setMainPlayerAudio(null); setStatus("已清空", "ok"); loadHistoryPage(0).catch(() => {}); } catch (err) { setError("清空失败：" + errorMessage(err)); } }); }
      const refreshCommunityBtnMobileEl = document.getElementById("refreshCommunityBtnMobile");
      if (refreshCommunityBtnMobileEl) { refreshCommunityBtnMobileEl.addEventListener("click", () => { loadCommunity().catch(e => setError(errorMessage(e))); }); }
      // --- End mobile form wiring ---
      userDropdownBtn.addEventListener("click", () => userDropdownMenu.classList.toggle("visible"));
      document.addEventListener("click", (e) => { if (!e.target.closest(".user-dropdown")) userDropdownMenu.classList.remove("visible"); });
      showAuthMode("login");
    
