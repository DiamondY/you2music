      /* ========================================
         State
         ======================================== */
      let authToken = localStorage.getItem("you2music.jwt") || "";
      let currentUser = null;
      let taskOffset = 0;
      const taskLimit = 20;
      let taskRefreshTimer = null;
      let apiLogOffset = 0;
      const apiLogLimit = 20;
      let apiLogRefreshTimer = null;
      let _lastApiLogs = [];

      /* ========================================
         DOM References
         ======================================== */
      const loginPage = document.getElementById("loginPage");
      const adminApp = document.getElementById("adminApp");
      const loginStatus = document.getElementById("loginStatus");
      const loginError = document.getElementById("loginError");
      const usersOut = document.getElementById("usersOut");
      const inviteOut = document.getElementById("inviteOut");
      const inviteStatus = document.getElementById("inviteStatus");
      const configJson = document.getElementById("configJson");
      const configStatus = document.getElementById("configStatus");
      const configError = document.getElementById("configError");
      const testOut = document.getElementById("testOut");
      const tasksOut = document.getElementById("tasksOut");
      const tasksPagination = document.getElementById("tasksPagination");
      const taskStatusFilter = document.getElementById("taskStatusFilter");
      const reloadTasksBtn = document.getElementById("reloadTasksBtn");
      const apiLogsOut = document.getElementById("apiLogsOut");
      const apiLogsPagination = document.getElementById("apiLogsPagination");
      const apiLogProviderFilter = document.getElementById("apiLogProviderFilter");
      const apiLogStatusFilter = document.getElementById("apiLogStatusFilter");
      const reloadApiLogsBtn = document.getElementById("reloadApiLogsBtn");

      /* ========================================
         API Helper
         ======================================== */
      async function fetchJson(url, opts) {
        const nextOpts = Object.assign({}, opts || {});
        const headers = Object.assign({}, nextOpts.headers || {});
        if (authToken) headers.Authorization = `Bearer ${authToken}`;
        nextOpts.headers = headers;
        const res = await fetch(url, nextOpts);
        const text = await res.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
        if (!res.ok) throw new Error(formatApiError(data, text || `HTTP ${res.status}`));
        return data;
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
        const labels = {
          username: "用户名",
          password: "密码",
          invite_code: "邀请码",
          old_password: "当前密码",
          new_password: "新密码"
        };
        return labels[field] || field || "输入";
      }

      function formatValidationItem(field, item) {
        const label = fieldLabel(field);
        const type = item.type || "";
        const ctx = item.ctx || {};
        if (type === "missing") return `请填写${label}`;
        if (type === "string_too_short") return `${label}至少需要 ${ctx.min_length || 1} 个字符`;
        if (type === "string_too_long") return `${label}不能超过 ${ctx.max_length || "限制"} 个字符`;
        if (type === "string_pattern_mismatch") return `${label}格式不正确`;
        if (type === "string_type") return `${label}必须是文本`;
        return `${label}: ${item.msg || item.message || "输入不符合要求"}`;
      }

      function errorMessage(err) {
        return err && err.message ? String(err.message) : String(err || "请求失败");
      }

      /* ========================================
         Session Management
         ======================================== */
      function setSession(token, user) {
        authToken = token || "";
        currentUser = user || null;
        if (authToken) localStorage.setItem("you2music.jwt", authToken);
        else localStorage.removeItem("you2music.jwt");
        const ok = Boolean(authToken && currentUser && currentUser.role === "admin");
        loginPage.classList.toggle("hidden", ok);
        adminApp.classList.toggle("hidden", !ok);
        if (ok) {
          const name = currentUser.username || "Admin";
          document.getElementById("sidebarUsername").textContent = name;
          document.getElementById("sidebarRole").textContent = currentUser.role === "admin" ? "管理员" : currentUser.role;
          document.getElementById("sidebarAvatar").textContent = name.charAt(0).toUpperCase();
        }
      }

      async function login() {
        loginError.classList.add("hidden");
        loginStatus.textContent = "登录中…";
        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value;
        const data = await fetchJson("/api/auth/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ username, password })
        });
        if (!data.user || data.user.role !== "admin") throw new Error("当前账户不是管理员");
        setSession(data.token, data.user);
        loginStatus.textContent = "";
        await Promise.all([loadUsers(), loadInviteCodes(), loadConfig(), loadTasks()]);
      }

      async function initSession() {
        if (!authToken) {
          setSession("", null);
          return;
        }
        try {
          const data = await fetchJson("/api/auth/me");
          if (!data.user || data.user.role !== "admin") throw new Error("not admin");
          setSession(authToken, data.user);
          await Promise.all([loadUsers(), loadInviteCodes(), loadConfig(), loadTasks()]);
        } catch {
          setSession("", null);
        }
      }

      /* ========================================
         Sidebar Navigation
         ======================================== */
      function switchSection(sectionId) {
        // Clean up task refresh timer when leaving tasks section
        const prevSection = document.querySelector(".section-panel.active");
        if (prevSection && prevSection.id === "section-tasks" && sectionId !== "tasks") {
          if (taskRefreshTimer) { clearTimeout(taskRefreshTimer); taskRefreshTimer = null; }
        }
        document.querySelectorAll(".nav-item").forEach(btn => {
          btn.classList.toggle("active", btn.getAttribute("data-section") === sectionId);
        });
        document.querySelectorAll(".section-panel").forEach(panel => {
          panel.classList.toggle("active", panel.id === `section-${sectionId}`);
        });
        // Close sidebar on mobile
        document.getElementById("adminSidebar").classList.remove("open");
        document.getElementById("sidebarOverlay").classList.remove("visible");
        // Auto-load tasks when switching to tasks section
        if (sectionId === "tasks") loadTasks();
        // Auto-load API logs when switching to api-logs section
        if (sectionId === "api-logs") loadApiLogs();
        // Clean up API log refresh timer when leaving api-logs section
        if (prevSection && prevSection.id === "section-api-logs" && sectionId !== "api-logs") {
          if (apiLogRefreshTimer) { clearTimeout(apiLogRefreshTimer); apiLogRefreshTimer = null; }
        }
      }

      document.querySelectorAll(".nav-item[data-section]").forEach(btn => {
        btn.addEventListener("click", () => switchSection(btn.getAttribute("data-section")));
      });

      // Mobile sidebar toggle
      document.getElementById("sidebarToggle").addEventListener("click", () => {
        const sidebar = document.getElementById("adminSidebar");
        const overlay = document.getElementById("sidebarOverlay");
        sidebar.classList.toggle("open");
        overlay.classList.toggle("visible");
      });

      document.getElementById("sidebarOverlay").addEventListener("click", () => {
        document.getElementById("adminSidebar").classList.remove("open");
        document.getElementById("sidebarOverlay").classList.remove("visible");
      });

      /* ========================================
         Users Management
         ======================================== */
      function escapeHtml(s) {
        return String(s || "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
      }

      async function loadUsers() {
        usersOut.innerHTML = '<div class="empty-state"><div>加载中…</div></div>';
        const data = await fetchJson("/api/admin/users");
        const users = data.users || [];
        if (!users.length) {
          usersOut.innerHTML = '<div class="empty-state"><svg class="icon" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg><div>暂无用户</div></div>';
          return;
        }
        const isMobile = window.innerWidth <= 768;
        const wrapClass = isMobile ? 'table-wrap table-wrap-mobile' : 'table-wrap';
        const rows = users.map(u => {
          const roleBadge = u.role === "admin"
            ? `<span class="cell-badge badge-admin">admin</span>`
            : `<span class="cell-badge badge-user">user</span>`;
          return `
          <tr data-user-id="${u.id}">
            <td data-label="ID"><span class="cell-id">${u.id}</span></td>
            <td data-label="用户名"><span class="cell-username">${escapeHtml(u.username)}</span></td>
            <td data-label="角色">
              <select data-field="role">
                <option value="user" ${u.role === "user" ? "selected" : ""}>user</option>
                <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
              </select>
            </td>
            <td data-label="每日配额"><input type="number" min="0" data-field="daily_quota" value="${u.daily_quota}"></td>
            <td data-label="禁用"><input type="checkbox" data-field="disabled" ${u.disabled ? "checked" : ""}></td>
            <td data-label="操作" class="cell-actions">
              <button class="btn btn-sm btn-outline" data-action="save">保存</button>
              <button class="btn btn-sm btn-warning" data-action="reset-password">重置密码</button>
              <button class="btn btn-sm btn-danger" data-action="delete">删除</button>
            </td>
          </tr>`;
        }).join("");
        usersOut.innerHTML = `<div class="${wrapClass}"><table><thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>每日配额</th><th>禁用</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table></div>`;
      }

      async function saveUser(row) {
        const userId = row.getAttribute("data-user-id");
        const role = row.querySelector('[data-field="role"]').value;
        const daily_quota = parseInt(row.querySelector('[data-field="daily_quota"]').value, 10);
        const disabled = row.querySelector('[data-field="disabled"]').checked;
        await fetchJson(`/api/admin/users/${userId}`, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ role, daily_quota, disabled })
        });
        await loadUsers();
      }

      async function deleteUser(row) {
        const userId = row.getAttribute("data-user-id");
        if (!window.confirm("确定删除该用户？")) return;
        await fetchJson(`/api/admin/users/${userId}`, { method: "DELETE" });
        await loadUsers();
      }

      async function resetPassword(row) {
        const userId = row.getAttribute("data-user-id");
        const username = row.querySelector(".cell-username").textContent;
        const newPwd = prompt(`为用户 ${username} 设置新密码（至少6位）：`);
        if (!newPwd) return;
        if (newPwd.length < 6) { alert("密码长度至少6位"); return; }
        await fetchJson(`/api/admin/users/${userId}`, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ reset_password: newPwd })
        });
        alert("密码已重置，用户下次登录需修改密码");
        await loadUsers();
      }

      /* ========================================
         Invite Codes
         ======================================== */
      async function loadInviteCodes() {
        const data = await fetchJson("/api/admin/invite-codes");
        const codes = data.invite_codes || [];
        if (!codes.length) {
          inviteOut.innerHTML = '<div class="empty-state"><svg class="icon" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg><div>暂无邀请码</div></div>';
          return;
        }
        inviteOut.innerHTML = '<div class="invite-list">' + codes.map(c => {
          const isUsed = Boolean(c.used_by);
          const statusClass = isUsed ? 'used' : 'unused';
          const statusText = isUsed ? `已使用 · 用户 ${c.used_by}` : '未使用';
          return `<div class="invite-item">
            <span class="invite-code">${escapeHtml(c.code)}</span>
            <span class="invite-status ${statusClass}">${statusText}</span>
          </div>`;
        }).join("") + '</div>';
      }

      async function createInviteCode() {
        inviteStatus.textContent = "生成中…";
        inviteStatus.classList.remove("success", "error");
        const data = await fetchJson("/api/admin/invite-codes", { method: "POST" });
        const code = data.invite_code && data.invite_code.code ? data.invite_code.code : "";
        inviteStatus.textContent = `新邀请码：${code}`;
        inviteStatus.classList.add("success");
        await loadInviteCodes();
      }

      /* ========================================
         Config Management
         ======================================== */
      async function loadConfig() {
        configError.classList.add("hidden");
        configStatus.textContent = "加载配置中…";
        configStatus.classList.remove("success", "error");
        const data = await fetchJson("/api/admin/config");
        configJson.value = JSON.stringify(data.config || {}, null, 2);
        configStatus.textContent = "配置已加载";
        configStatus.classList.add("success");
      }

      async function saveConfig() {
        configError.classList.add("hidden");
        configStatus.textContent = "保存配置中…";
        configStatus.classList.remove("success", "error");
        let cfg;
        try { cfg = JSON.parse(configJson.value || "{}"); } catch (e) { throw new Error("JSON 解析失败: " + e); }
        if (cfg && typeof cfg === "object") delete cfg.admin_token;
        await fetchJson("/api/admin/config", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ config: cfg })
        });
        configStatus.textContent = "配置已保存";
        configStatus.classList.add("success");
      }

      async function reloadConfig() {
        configStatus.textContent = "应用中…";
        configStatus.classList.remove("success", "error");
        await fetchJson("/api/admin/reload", { method: "POST" });
        configStatus.textContent = "已应用";
        configStatus.classList.add("success");
      }

      async function runTest() {
        configStatus.textContent = "测试中…";
        configStatus.classList.remove("success", "error");
        testOut.classList.remove("hidden");
        const data = await fetchJson("/api/admin/test", { method: "POST" });
        testOut.textContent = JSON.stringify(data, null, 2);
        configStatus.textContent = "测试完成";
        configStatus.classList.add("success");
      }

      /* ========================================
         Tasks Management
         ======================================== */
      function statusLabel(s) {
        const map = { queued: "排队中", running: "生成中", succeeded: "已完成", failed: "失败" };
        return map[s] || s;
      }

      function formatTime(ms) {
        if (!ms) return "-";
        const d = new Date(ms);
        const pad = n => String(n).padStart(2, "0");
        return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
      }

      function renderTaskPagination(total) {
        const start = total === 0 ? 0 : taskOffset + 1;
        const end = Math.min(taskOffset + taskLimit, total);
        let html = `<span>第 ${start}-${end} 条 / 共 ${total} 条</span><span>`;
        if (taskOffset > 0) html += `<button class="btn btn-secondary" data-action="prev-page" style="min-height:32px;padding:2px 12px;font-size:12px;">上一页</button> `;
        if (end < total) html += `<button class="btn btn-secondary" data-action="next-page" style="min-height:32px;padding:2px 12px;font-size:12px;">下一页</button>`;
        html += "</span>";
        tasksPagination.innerHTML = html;
      }

      function scheduleTaskRefresh(jobs) {
        if (taskRefreshTimer) { clearTimeout(taskRefreshTimer); taskRefreshTimer = null; }
        const hasActive = jobs && jobs.some(j => j.status === "queued" || j.status === "running");
        if (hasActive) {
          taskRefreshTimer = setTimeout(() => loadTasks(), 5000);
        }
      }

      async function loadTasks() {
        const status = taskStatusFilter.value || "";
        const params = new URLSearchParams({ offset: String(taskOffset), limit: String(taskLimit) });
        if (status) params.set("status", status);
        const data = await fetchJson(`/api/admin/jobs?${params}`);
        const jobs = data.jobs || [];
        const total = data.total || 0;
        if (!jobs.length) {
          tasksOut.innerHTML = '<div class="empty-state"><svg class="icon" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg><div>暂无任务</div></div>';
          renderTaskPagination(0);
          scheduleTaskRefresh(null);
          return;
        }
        const isMobile = window.innerWidth < 768;
        let html = '<div class="table-wrap"><table><thead><tr>'
          + '<th>ID</th><th>用户</th><th>Provider</th><th>状态</th><th>提示词</th>'
          + (isMobile ? '' : '<th>队列</th>')
          + '<th>创建时间</th><th>操作</th></tr></thead><tbody>';
        for (const j of jobs) {
          const shortId = j.job_id ? j.job_id.substring(0, 8) : "-";
          const badgeClass = `badge-${j.status}`;
          const promptText = j.prompt && j.prompt.length > 60 ? j.prompt.substring(0, 60) + "…" : (j.prompt || "-");
          const queueInfo = (j.status === "queued" && j.queue_position) ? `${j.queue_position}/${j.queue_depth || "-"}` : "-";
          const cancelBtn = j.status === "queued"
            ? `<button class="btn btn-secondary" data-action="cancel" data-id="${j.job_id}" style="min-height:28px;padding:2px 8px;font-size:12px;">取消</button>` : "";
          const deleteBtn = `<button class="btn btn-secondary" data-action="delete-task" data-id="${j.job_id}" style="min-height:28px;padding:2px 8px;font-size:12px;">删除</button>`;
          html += `<tr>`
            + `<td data-label="ID" title="${escapeHtml(j.job_id || "")}">${escapeHtml(shortId)}</td>`
            + `<td data-label="用户">${escapeHtml(j.username || "-")}</td>`
            + `<td data-label="Provider">${escapeHtml(j.provider || "-")}</td>`
            + `<td data-label="状态"><span class="badge ${badgeClass}">${statusLabel(j.status)}</span></td>`
            + `<td data-label="提示词" title="${escapeHtml(j.prompt || "")}">${escapeHtml(promptText)}</td>`
            + (isMobile ? '' : `<td data-label="队列">${queueInfo}</td>`)
            + `<td data-label="创建时间">${formatTime(j.created_at_ms)}</td>`
            + `<td data-label="操作">${cancelBtn} ${deleteBtn}</td>`
            + `</tr>`;
        }
        html += '</tbody></table></div>';
        tasksOut.innerHTML = html;
        renderTaskPagination(total);
        scheduleTaskRefresh(jobs);
      }

      // Task table action delegation
      tasksOut.addEventListener("click", async e => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const action = btn.getAttribute("data-action");
        const jobId = btn.getAttribute("data-id");
        if (action === "cancel") {
          if (!confirm(`确认取消任务 ${jobId ? jobId.substring(0, 8) : ""}？`)) return;
          try { await fetchJson(`/api/admin/jobs/${jobId}/cancel`, { method: "POST" }); } catch (err) { alert(String(err)); return; }
          await loadTasks();
        } else if (action === "delete-task") {
          if (!confirm(`确认删除任务 ${jobId ? jobId.substring(0, 8) : ""}？此操作不可撤销。`)) return;
          try { await fetchJson(`/api/admin/jobs/${jobId}`, { method: "DELETE" }); } catch (err) { alert(String(err)); return; }
          await loadTasks();
        }
      });

      // Task pagination
      tasksPagination.addEventListener("click", e => {
        const action = e.target.getAttribute("data-action");
        if (action === "prev-page") { taskOffset = Math.max(0, taskOffset - taskLimit); loadTasks(); }
        if (action === "next-page") { taskOffset += taskLimit; loadTasks(); }
      });

      // Task filter & refresh
      taskStatusFilter.addEventListener("change", () => { taskOffset = 0; loadTasks(); });
      reloadTasksBtn.addEventListener("click", () => loadTasks());

      /* ========================================
         API Logs Management
         ======================================== */
      function httpStatusLabel(status) {
        if (!status) return "-";
        if (status >= 200 && status < 300) return `<span style="color:var(--color-success)">${status}</span>`;
        if (status === 429) return `<span style="color:var(--color-warning)">${status} 限流</span>`;
        if (status >= 400 && status < 500) return `<span style="color:var(--color-error)">${status} 错误</span>`;
        if (status >= 500) return `<span style="color:var(--color-error)">${status} 服务器错误</span>`;
        return String(status);
      }

      function renderApiLogPagination(total) {
        const start = total === 0 ? 0 : apiLogOffset + 1;
        const end = Math.min(apiLogOffset + apiLogLimit, total);
        let html = `<span>第 ${start}-${end} 条 / 共 ${total} 条</span><span>`;
        if (apiLogOffset > 0) html += `<button class="btn btn-secondary" data-action="prev-page" style="min-height:32px;padding:2px 12px;font-size:12px;">上一页</button> `;
        if (end < total) html += `<button class="btn btn-secondary" data-action="next-page" style="min-height:32px;padding:2px 12px;font-size:12px;">下一页</button>`;
        html += "</span>";
        apiLogsPagination.innerHTML = html;
      }

      function scheduleApiLogRefresh(jobs) {
        if (apiLogRefreshTimer) { clearTimeout(apiLogRefreshTimer); apiLogRefreshTimer = null; }
        const hasActive = jobs && jobs.some(j => j.status === "queued" || j.status === "running");
        if (hasActive) {
          apiLogRefreshTimer = setTimeout(() => loadApiLogs(), 8000);
        }
      }

      async function loadApiLogs() {
        const provider = apiLogProviderFilter.value || "";
        let httpStatus = null;
        let httpStatusFamily = null;
        const statusVal = apiLogStatusFilter.value || "";
        if (statusVal === "2xx") httpStatusFamily = 2;
        else if (statusVal === "429") httpStatus = 429;
        else if (statusVal === "4xx") httpStatusFamily = 4;
        else if (statusVal === "5xx") httpStatusFamily = 5;

        const params = new URLSearchParams({ offset: String(apiLogOffset), limit: String(apiLogLimit) });
        if (provider) params.set("provider", provider);
        if (httpStatus !== null) params.set("http_status", String(httpStatus));
        if (httpStatusFamily !== null) params.set("http_status_family", String(httpStatusFamily));
        const data = await fetchJson(`/api/admin/api-logs?${params}`);
        const logs = data.logs || [];
        const total = data.total || 0;
        if (!logs.length) {
          apiLogsOut.innerHTML = '<div class="empty-state"><svg class="icon" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg><div>暂无日志记录</div></div>';
          renderApiLogPagination(0);
          _lastApiLogs = [];
          return;
        }
        const isMobile = window.innerWidth < 768;
        let html = '<div class="table-wrap"><table><thead><tr>'
          + '<th>时间</th><th>Provider</th><th>任务ID</th><th>端点</th><th>状态</th><th>耗时</th><th>Key</th><th>操作</th></tr></thead><tbody>';
        for (const log of logs) {
          const shortJobId = log.job_id ? log.job_id.substring(0, 8) : "-";
          const elapsed = log.elapsed_ms != null ? `${log.elapsed_ms}ms` : "-";
          const keyHint = log.api_key_hint || "-";
          const shortEndpoint = log.endpoint || "-";
          const statusBadge = httpStatusLabel(log.http_status);
          const detailBtn = `<button class="btn btn-secondary" data-action="detail" data-id="${log.id}" style="min-height:28px;padding:2px 8px;font-size:12px;">查看详情</button>`;
          html += `<tr>`
            + `<td data-label="时间">${formatTime(log.created_at_ms)}</td>`
            + `<td data-label="Provider">${escapeHtml(log.provider || "-")}</td>`
            + `<td data-label="任务ID" title="${escapeHtml(log.job_id || "")}">${escapeHtml(shortJobId)}</td>`
            + `<td data-label="端点" title="${escapeHtml(shortEndpoint)}">${escapeHtml(shortEndpoint)}</td>`
            + `<td data-label="状态">${statusBadge}</td>`
            + `<td data-label="耗时">${escapeHtml(elapsed)}</td>`
            + `<td data-label="Key">${escapeHtml(keyHint)}</td>`
            + `<td data-label="操作">${detailBtn}</td>`
            + `</tr>`;
        }
        html += '</tbody></table></div>';
        apiLogsOut.innerHTML = html;
        renderApiLogPagination(total);
        _lastApiLogs = logs;
      }

      function renderApiLogDetail(log) {
        const pretty = (raw) => {
          if (!raw) return "<em style='color:var(--color-text-muted)'>（无）</em>";
          try {
            // Always escape HTML, even for JSON, because this will be inserted via innerHTML.
            return escapeHtml(JSON.stringify(JSON.parse(raw), null, 2));
          } catch {
            return escapeHtml(raw);
          }
        };
        return `
        <div id="apiLogModal" style="position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.7);">
          <div style="background:var(--color-bg-card-solid, #252542);border-radius:var(--radius-lg);padding:var(--space-xl);width:min(700px,90vw);max-height:90vh;overflow-y:auto;box-shadow:var(--glass-shadow, 0 8px 32px rgba(0,0,0,0.4));border:1px solid var(--glass-border, rgba(255,255,255,0.1));">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-lg);">
              <div style="font-size:16px;font-weight:600;color:var(--color-text-primary);">API 日志详情</div>
              <button id="closeApiLogModal" style="background:none;border:none;cursor:pointer;color:var(--color-text-secondary);font-size:24px;line-height:1;">&times;</button>
            </div>
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);white-space:nowrap;">时间</td><td style="padding:6px 8px;color:var(--color-text-primary);">${formatTime(log.created_at_ms)}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">Provider</td><td style="padding:6px 8px;color:var(--color-text-primary);">${escapeHtml(log.provider || "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">任务ID</td><td style="padding:6px 8px;font-family:var(--font-mono);font-size:12px;word-break:break-all;color:var(--color-text-primary);">${escapeHtml(log.job_id || "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">端点</td><td style="padding:6px 8px;font-family:var(--font-mono);font-size:12px;color:var(--color-text-primary);">${escapeHtml(log.endpoint || "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">方法</td><td style="padding:6px 8px;color:var(--color-text-primary);">${escapeHtml(log.method || "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">Key</td><td style="padding:6px 8px;color:var(--color-text-primary);">${escapeHtml(log.api_key_hint || "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">耗时</td><td style="padding:6px 8px;color:var(--color-text-primary);">${escapeHtml(log.elapsed_ms != null ? log.elapsed_ms + "ms" : "-")}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">HTTP 状态</td><td style="padding:6px 8px;">${httpStatusLabel(log.http_status)}</td></tr>
              <tr><td style="padding:6px 8px;color:var(--color-text-muted);">错误</td><td style="padding:6px 8px;color:var(--color-error);font-size:12px;">${escapeHtml(log.error || "（无）")}</td></tr>
            </table>
            <div style="margin-top:var(--space-lg);">
              <div style="font-size:12px;font-weight:600;color:var(--color-text-muted);margin-bottom:var(--space-xs);">请求内容</div>
              <pre style="background:var(--color-bg-surface, rgba(255,255,255,0.04));border-radius:var(--radius-md);padding:var(--space-md);font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;word-break:break-all;max-height:200px;overflow-y:auto;margin:0;color:var(--color-text-secondary);">${pretty(log.request_body)}</pre>
            </div>
            <div style="margin-top:var(--space-lg);">
              <div style="font-size:12px;font-weight:600;color:var(--color-text-muted);margin-bottom:var(--space-xs);">响应内容</div>
              <pre style="background:var(--color-bg-surface, rgba(255,255,255,0.04));border-radius:var(--radius-md);padding:var(--space-md);font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;word-break:break-all;max-height:200px;overflow-y:auto;margin:0;color:var(--color-text-secondary);">${pretty(log.response_body)}</pre>
            </div>
          </div>
        </div>`;
      }

      // API log table action delegation
      apiLogsOut.addEventListener("click", e => {
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const action = btn.getAttribute("data-action");
        if (action === "detail") {
          const logId = parseInt(btn.getAttribute("data-id"), 10);
          const log = _lastApiLogs.find(l => l.id === logId);
          if (log) {
            const overlay = document.createElement("div");
            overlay.innerHTML = renderApiLogDetail(log);
            document.body.appendChild(overlay);
            document.getElementById("closeApiLogModal").addEventListener("click", () => overlay.remove());
            overlay.addEventListener("click", e => { if (e.target === overlay) overlay.remove(); });
          }
        }
      });

      // API log pagination
      apiLogsPagination.addEventListener("click", e => {
        const action = e.target.getAttribute("data-action");
        if (action === "prev-page") { apiLogOffset = Math.max(0, apiLogOffset - apiLogLimit); loadApiLogs(); }
        if (action === "next-page") { apiLogOffset += apiLogLimit; loadApiLogs(); }
      });

      // API log filter & refresh
      apiLogProviderFilter.addEventListener("change", () => { apiLogOffset = 0; loadApiLogs(); });
      apiLogStatusFilter.addEventListener("change", () => { apiLogOffset = 0; loadApiLogs(); });
      reloadApiLogsBtn.addEventListener("click", () => loadApiLogs());

      /* ========================================
         Event Listeners
         ======================================== */
      document.getElementById("loginBtn").addEventListener("click", () => login().catch(e => {
        loginStatus.textContent = "";
        loginError.textContent = errorMessage(e);
        loginError.classList.remove("hidden");
      }));

      // Enter key on password field
      document.getElementById("password").addEventListener("keydown", e => {
        if (e.key === "Enter") document.getElementById("loginBtn").click();
      });

      document.getElementById("logoutBtn").addEventListener("click", () => setSession("", null));
      document.getElementById("reloadUsersBtn").addEventListener("click", () => loadUsers().catch(e => {
        usersOut.innerHTML = `<div class="error-message">${escapeHtml(String(e))}</div>`;
      }));
      document.getElementById("createInviteBtn").addEventListener("click", () => createInviteCode().catch(e => {
        inviteStatus.textContent = String(e);
        inviteStatus.classList.add("error");
      }));
      document.getElementById("loadConfigBtn").addEventListener("click", () => loadConfig().catch(e => {
        configError.textContent = String(e);
        configError.classList.remove("hidden");
      }));
      document.getElementById("saveConfigBtn").addEventListener("click", () => saveConfig().catch(e => {
        configError.textContent = String(e);
        configError.classList.remove("hidden");
        configStatus.textContent = "";
      }));
      document.getElementById("reloadConfigBtn").addEventListener("click", () => reloadConfig().catch(e => {
        configError.textContent = String(e);
        configError.classList.remove("hidden");
        configStatus.textContent = "";
      }));
      document.getElementById("testBtn").addEventListener("click", () => runTest().catch(e => {
        configError.textContent = String(e);
        configError.classList.remove("hidden");
        configStatus.textContent = "";
      }));

      // User table action delegation
      usersOut.addEventListener("click", e => {
        const action = e.target && e.target.getAttribute ? e.target.getAttribute("data-action") : "";
        if (!action) return;
        const row = e.target.closest("tr");
        if (action === "save") saveUser(row).catch(err => alert(String(err)));
        if (action === "reset-password") resetPassword(row).catch(err => alert(String(err)));
        if (action === "delete") deleteUser(row).catch(err => alert(String(err)));
      });

      // Re-render table on resize for mobile/desktop switch
      let resizeTimer;
      window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          if (currentUser && currentUser.role === "admin") {
            loadUsers().catch(() => {});
            const tasksSection = document.getElementById("section-tasks");
            if (tasksSection && tasksSection.classList.contains("active")) loadTasks().catch(() => {});
          }
        }, 300);
      });

      /* ========================================
         Init
         ======================================== */
      initSession();
    
