/**
 * ATC Status Card – Lovelace custom element
 * Shows system status: timer counts, sync status, errors.
 * Includes modal forms to add and remove calendar accounts directly from the dashboard.
 */
class AtcStatusCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._showAddModal = false;
  }

  setConfig(config) {
    this.config = config || {};
    this._title = this.config.title || "ATC System Status";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._showAddModal) {
      this.render();
    }
  }

  _gatherStats() {
    if (!this._hass) return {};
    const states = this._hass.states;
    let totalTimers = 0, enabledTimers = 0, runningTimers = 0, errorTimers = 0;
    const syncStatuses = [], errors = [];

    Object.keys(states).forEach((entityId) => {
      const state = states[entityId];
      if (entityId.startsWith("switch.") && entityId.includes("atc")) {
        totalTimers++;
        if (state.state === "on") enabledTimers++;
      }
      if (entityId.includes("_status") && entityId.includes("atc")) {
        const val = state.state;
        if (val === "running") runningTimers++;
        if (val === "error") {
          errorTimers++;
          errors.push(state.attributes.friendly_name || entityId);
        }
      }
      if (entityId.includes("atc") && entityId.includes("sync")) {
        syncStatuses.push({
          name: state.attributes.friendly_name || entityId,
          status: state.state,
          accountId: (state.attributes && state.attributes.account_id) || "",
          provider: (state.attributes && state.attributes.provider) || "",
        });
      }
    });

    return { totalTimers, enabledTimers, runningTimers, errorTimers, syncStatuses, errors };
  }

  _syncStatusIcon(status) {
    return { ok: "✅", syncing: "🔄", error: "❌", auth_error: "🔒", idle: "💤" }[status] || "❓";
  }

  _syncStatusColor(status) {
    return { ok: "#4CAF50", syncing: "#2196F3", error: "#f44336", auth_error: "#FF9800", idle: "#9E9E9E" }[status] || "#9E9E9E";
  }

  async _callService(domain, service, data) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      alert(`Fehler / Error (${service}): ${err.message || err}`);
    }
  }

  async _triggerSync() {
    await this._callService("advanced_timer_calendar", "sync_calendar", {});
  }

  async _removeAccount(accountId, name) {
    if (!confirm(`Kalender-Konto "${name}" entfernen?\nRemove calendar account "${name}"?`)) return;
    await this._callService("advanced_timer_calendar", "remove_calendar_account", { account_id: accountId });
  }

  async _submitAddAccount() {
    const sr = this.shadowRoot;
    const name = sr.querySelector('[name="ca-name"]').value.trim();
    const provider = sr.querySelector('[name="ca-provider"]').value;
    if (!name) { alert("Name ist erforderlich / Name is required"); return; }
    if (!provider) { alert("Anbieter ist erforderlich / Provider is required"); return; }

    const data = {
      name, provider,
      sync_direction: sr.querySelector('[name="ca-sync-dir"]').value,
      conflict_strategy: sr.querySelector('[name="ca-conflict"]').value,
    };

    const clientId = sr.querySelector('[name="ca-client-id"]').value.trim();
    const clientSecret = sr.querySelector('[name="ca-client-secret"]').value.trim();
    const tenantId = sr.querySelector('[name="ca-tenant-id"]').value.trim();
    const username = sr.querySelector('[name="ca-username"]').value.trim();
    const password = sr.querySelector('[name="ca-password"]').value.trim();
    const caldavUrl = sr.querySelector('[name="ca-caldav-url"]').value.trim();

    if (clientId) data.client_id = clientId;
    if (clientSecret) data.client_secret = clientSecret;
    if (tenantId) data.tenant_id = tenantId;
    if (username) data.username = username;
    if (password) data.password = password;
    if (caldavUrl) data.caldav_url = caldavUrl;

    await this._callService("advanced_timer_calendar", "add_calendar_account", data);
    this._showAddModal = false;
    this.render();
  }

  render() {
    if (!this.shadowRoot) return;

    const stats = this._gatherStats();
    const {
      totalTimers = 0, enabledTimers = 0, runningTimers = 0, errorTimers = 0,
      syncStatuses = [], errors = [],
    } = stats;

    const syncRows = syncStatuses.length === 0
      ? '<tr><td colspan="3" class="empty">Keine Kalender-Konten konfiguriert / No calendar accounts configured.</td></tr>'
      : syncStatuses.map((s) => `
          <tr>
            <td>${s.name}${s.provider ? ` <small>(${s.provider})</small>` : ""}</td>
            <td style="color:${this._syncStatusColor(s.status)}">${this._syncStatusIcon(s.status)} ${s.status}</td>
            <td>
              ${s.accountId
                ? `<button class="btn-sm del" data-id="${s.accountId}" data-name="${s.name.replace(/"/g, "&quot;")}">🗑</button>`
                : ""}
            </td>
          </tr>`).join("");

    const errorSection = errors.length === 0 ? "" : `
      <div class="error-box">
        <strong>⚠️ Errors:</strong>
        <ul>${errors.map((e) => `<li>${e}</li>`).join("")}</ul>
      </div>`;

    const modalHtml = this._showAddModal ? `
      <div class="modal-overlay" id="ca-modal-overlay">
        <div class="modal">
          <div class="modal-header">
            <h3>Kalender-Konto hinzufügen / Add Calendar Account</h3>
            <button class="close-btn" id="ca-modal-close">×</button>
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>Name *</label>
              <input type="text" name="ca-name" placeholder="z.B. Mein Google Kalender" required/>
            </div>
            <div class="form-row">
              <label>Anbieter / Provider *</label>
              <select name="ca-provider" id="ca-provider-sel">
                <option value="google">Google</option>
                <option value="microsoft">Microsoft 365</option>
                <option value="apple">Apple / CalDAV</option>
              </select>
            </div>
            <div class="form-row">
              <label>Sync-Richtung / Sync Direction</label>
              <select name="ca-sync-dir">
                <option value="bidirectional">↔ Bidirektional / Bidirectional</option>
                <option value="inbound">↓ Nur empfangen / Inbound only</option>
                <option value="outbound">↑ Nur senden / Outbound only</option>
              </select>
            </div>
            <div class="form-row">
              <label>Konflikt-Strategie / Conflict Strategy</label>
              <select name="ca-conflict">
                <option value="newest_wins">Neuestes gewinnt / Newest wins</option>
                <option value="ha_wins">HA gewinnt / HA wins</option>
                <option value="remote_wins">Extern gewinnt / Remote wins</option>
              </select>
            </div>
            <div id="ca-oauth-fields">
              <div class="form-row">
                <label>Client ID (Google / Microsoft)</label>
                <input type="text" name="ca-client-id" placeholder="OAuth Client ID"/>
              </div>
              <div class="form-row">
                <label>Client Secret (Google / Microsoft)</label>
                <input type="password" name="ca-client-secret" placeholder="OAuth Client Secret"/>
              </div>
              <div class="form-row" id="ca-grp-tenant">
                <label>Tenant ID (nur Microsoft / Microsoft only)</label>
                <input type="text" name="ca-tenant-id" placeholder="Azure Tenant ID"/>
              </div>
            </div>
            <div id="ca-caldav-fields" style="display:none">
              <div class="form-row">
                <label>Benutzername / Username</label>
                <input type="text" name="ca-username" placeholder="Apple ID / CalDAV Username"/>
              </div>
              <div class="form-row">
                <label>Passwort / Password</label>
                <input type="password" name="ca-password" placeholder="App-spezifisches Passwort / App-specific password"/>
              </div>
              <div class="form-row">
                <label>CalDAV URL (Apple / Generic)</label>
                <input type="text" name="ca-caldav-url" placeholder="https://caldav.icloud.com/"/>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn cancel" id="ca-modal-cancel">Abbrechen / Cancel</button>
            <button class="btn submit" id="ca-modal-submit">Hinzufügen / Add</button>
          </div>
        </div>
      </div>` : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12)); padding: 16px; }
        h2 { margin: 0 0 16px; font-size: 1.1em; color: var(--primary-text-color); }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
        .stat-box { background: var(--secondary-background-color, #f5f5f5); border-radius: 8px; padding: 12px; text-align: center; }
        .stat-value { font-size: 2em; font-weight: 700; color: var(--primary-color, #03a9f4); }
        .stat-label { font-size: 0.8em; color: var(--secondary-text-color); margin-top: 2px; }
        .stat-box.running .stat-value { color: #4CAF50; }
        .stat-box.error .stat-value { color: #f44336; }
        .section-header { display: flex; justify-content: space-between; align-items: center; }
        h3 { font-size: 0.95em; margin: 12px 0 6px; color: var(--primary-text-color); }
        table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        td { padding: 5px 8px; border-bottom: 1px solid var(--divider-color, #f0f0f0); }
        td small { color: var(--secondary-text-color); }
        .empty { text-align: center; color: var(--secondary-text-color); padding: 10px; }
        .error-box { background: rgba(244,67,54,.07); border-radius: 8px; padding: 10px 12px; margin-top: 12px; font-size: 0.87em; }
        .error-box ul { margin: 4px 0 0; padding-left: 16px; }
        .sync-btn { display: block; width: 100%; margin-top: 12px; padding: 8px;
          background: var(--primary-color, #03a9f4); color: white; border: none;
          border-radius: 6px; cursor: pointer; font-size: 0.9em; transition: opacity .2s; }
        .sync-btn:hover { opacity: 0.8; }
        .btn { border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer;
          font-size: 0.85em; background: var(--primary-color, #03a9f4); color: white; transition: opacity .2s; }
        .btn:hover { opacity: 0.8; }
        .btn.add { background: #4CAF50; padding: 4px 10px; font-size: 0.8em; }
        .btn.cancel { background: #9e9e9e; }
        .btn.submit { background: var(--primary-color, #03a9f4); }
        .btn-sm { border: none; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.8em; background: #f44336; color: white; }
        /* Modal */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 9999;
          display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box; }
        .modal { background: var(--card-background-color, #1c1c1c); border-radius: 12px;
          min-width: 300px; max-width: 480px; width: 100%; max-height: 90vh; overflow-y: auto;
          box-shadow: 0 8px 32px rgba(0,0,0,.4); }
        .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--divider-color, #333); }
        .modal-header h3 { margin: 0; font-size: 1em; color: var(--primary-text-color); }
        .close-btn { background: none; border: none; font-size: 1.5em; cursor: pointer; color: var(--secondary-text-color); line-height: 1; padding: 0 4px; }
        .modal-body { padding: 16px; }
        .modal-footer { padding: 8px 16px 16px; display: flex; justify-content: flex-end; gap: 8px; }
        .form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
        .form-row label { font-size: 0.85em; color: var(--secondary-text-color); font-weight: 500; }
        .form-row input,.form-row select {
          padding: 7px 10px; border: 1px solid var(--divider-color, #444);
          border-radius: 6px; background: var(--secondary-background-color, #2a2a2a);
          color: var(--primary-text-color); font-size: 0.9em; box-sizing: border-box; width: 100%; }
      </style>
      <div class="card">
        <h2>${this._title}</h2>
        <div class="stats-grid">
          <div class="stat-box"><div class="stat-value">${totalTimers}</div><div class="stat-label">Total Timers</div></div>
          <div class="stat-box enabled"><div class="stat-value">${enabledTimers}</div><div class="stat-label">Enabled</div></div>
          <div class="stat-box running"><div class="stat-value">${runningTimers}</div><div class="stat-label">Running</div></div>
          <div class="stat-box error"><div class="stat-value">${errorTimers}</div><div class="stat-label">Errors</div></div>
        </div>

        <div class="section-header">
          <h3>📅 Kalender-Konten / Calendar Accounts</h3>
          <button class="btn add" id="btn-add-account">➕ Konto hinzufügen / Add Account</button>
        </div>
        <table>
          <tbody>${syncRows}</tbody>
        </table>

        ${errorSection}

        <button class="sync-btn" id="sync-btn">🔄 Jetzt synchronisieren / Sync Calendars Now</button>
      </div>
      ${modalHtml}`;

    const syncBtn = this.shadowRoot.getElementById("sync-btn");
    if (syncBtn) syncBtn.addEventListener("click", () => this._triggerSync());

    const addBtn = this.shadowRoot.getElementById("btn-add-account");
    if (addBtn) addBtn.addEventListener("click", () => {
      this._showAddModal = true;
      this.render();
    });

    this.shadowRoot.querySelectorAll(".btn-sm.del").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        await this._removeAccount(e.target.dataset.id, e.target.dataset.name);
      });
    });

    if (this._showAddModal) {
      const close = this.shadowRoot.getElementById("ca-modal-close");
      const cancel = this.shadowRoot.getElementById("ca-modal-cancel");
      const submit = this.shadowRoot.getElementById("ca-modal-submit");
      const overlay = this.shadowRoot.getElementById("ca-modal-overlay");
      const providerSel = this.shadowRoot.getElementById("ca-provider-sel");

      const closeModal = () => { this._showAddModal = false; this.render(); };
      if (close) close.addEventListener("click", closeModal);
      if (cancel) cancel.addEventListener("click", closeModal);
      if (overlay) overlay.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });
      if (submit) submit.addEventListener("click", () => this._submitAddAccount());

      if (providerSel) {
        providerSel.addEventListener("change", (e) => {
          const isApple = e.target.value === "apple";
          const isMicrosoft = e.target.value === "microsoft";
          const oauthFields = this.shadowRoot.getElementById("ca-oauth-fields");
          const caldavFields = this.shadowRoot.getElementById("ca-caldav-fields");
          const tenantGrp = this.shadowRoot.getElementById("ca-grp-tenant");
          if (oauthFields) oauthFields.style.display = isApple ? "none" : "block";
          if (caldavFields) caldavFields.style.display = isApple ? "block" : "none";
          if (tenantGrp) tenantGrp.style.display = isMicrosoft ? "flex" : "none";
        });
      }
    }
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("atc-status-card", AtcStatusCard);
