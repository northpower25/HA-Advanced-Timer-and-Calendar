/**
 * ATC Status Card – Lovelace custom element
 * Shows system status: timer counts, sync status, errors.
 */
class AtcStatusCard extends HTMLElement {
  static get properties() {
    return {
      hass: Object,
      config: Object,
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this.config = config || {};
    this._title = this.config.title || "ATC System Status";
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  _gatherStats() {
    if (!this._hass) return {};
    const states = this._hass.states;

    let totalTimers = 0;
    let enabledTimers = 0;
    let runningTimers = 0;
    let errorTimers = 0;
    const syncStatuses = [];
    const errors = [];

    Object.keys(states).forEach((entityId) => {
      const state = states[entityId];

      // Count switch entities (timers)
      if (entityId.startsWith("switch.") && entityId.includes("atc")) {
        totalTimers++;
        if (state.state === "on") enabledTimers++;
      }

      // Count status sensors
      if (entityId.includes("_status") && entityId.includes("atc")) {
        const val = state.state;
        if (val === "running") runningTimers++;
        if (val === "error") {
          errorTimers++;
          errors.push(state.attributes.friendly_name || entityId);
        }
      }

      // Sync status sensors
      if (entityId.includes("atc_sync") || (entityId.includes("atc") && entityId.includes("sync"))) {
        syncStatuses.push({
          name: state.attributes.friendly_name || entityId,
          status: state.state,
        });
      }
    });

    return { totalTimers, enabledTimers, runningTimers, errorTimers, syncStatuses, errors };
  }

  _syncStatusIcon(status) {
    const icons = {
      ok: "✅",
      syncing: "🔄",
      error: "❌",
      auth_error: "🔒",
      idle: "💤",
    };
    return icons[status] || "❓";
  }

  _syncStatusColor(status) {
    const colors = {
      ok: "#4CAF50",
      syncing: "#2196F3",
      error: "#f44336",
      auth_error: "#FF9800",
      idle: "#9E9E9E",
    };
    return colors[status] || "#9E9E9E";
  }

  async _triggerSync() {
    if (!this._hass) return;
    await this._hass.callService("advanced_timer_calendar", "sync_calendar", {});
  }

  render() {
    if (!this.shadowRoot) return;

    const stats = this._gatherStats();
    const {
      totalTimers = 0,
      enabledTimers = 0,
      runningTimers = 0,
      errorTimers = 0,
      syncStatuses = [],
      errors = [],
    } = stats;

    const syncRows = syncStatuses.length === 0
      ? '<tr><td colspan="2" class="empty">No calendar accounts configured.</td></tr>'
      : syncStatuses.map((s) => `
          <tr>
            <td>${s.name}</td>
            <td style="color:${this._syncStatusColor(s.status)}">
              ${this._syncStatusIcon(s.status)} ${s.status}
            </td>
          </tr>`).join("");

    const errorSection = errors.length === 0 ? "" : `
      <div class="error-box">
        <strong>⚠️ Errors:</strong>
        <ul>${errors.map((e) => `<li>${e}</li>`).join("")}</ul>
      </div>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12));
          padding: 16px; }
        h2 { margin: 0 0 16px; font-size: 1.1em; color: var(--primary-text-color); }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
          margin-bottom: 16px; }
        .stat-box { background: var(--secondary-background-color, #f5f5f5); border-radius: 8px;
          padding: 12px; text-align: center; }
        .stat-value { font-size: 2em; font-weight: 700; color: var(--primary-color, #03a9f4); }
        .stat-label { font-size: 0.8em; color: var(--secondary-text-color); margin-top: 2px; }
        .stat-box.running .stat-value { color: #4CAF50; }
        .stat-box.error .stat-value { color: #f44336; }
        .stat-box.enabled .stat-value { color: var(--primary-color, #03a9f4); }
        h3 { font-size: 0.95em; margin: 12px 0 6px; color: var(--primary-text-color); }
        table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        td { padding: 5px 8px; border-bottom: 1px solid var(--divider-color, #f0f0f0); }
        .empty { text-align: center; color: var(--secondary-text-color); padding: 10px; }
        .error-box { background: rgba(244,67,54,.07); border-radius: 8px;
          padding: 10px 12px; margin-top: 12px; font-size: 0.87em; }
        .error-box ul { margin: 4px 0 0; padding-left: 16px; }
        .sync-btn { display: block; width: 100%; margin-top: 12px; padding: 8px;
          background: var(--primary-color, #03a9f4); color: white; border: none;
          border-radius: 6px; cursor: pointer; font-size: 0.9em; transition: opacity .2s; }
        .sync-btn:hover { opacity: 0.8; }
      </style>
      <div class="card">
        <h2>${this._title}</h2>
        <div class="stats-grid">
          <div class="stat-box">
            <div class="stat-value">${totalTimers}</div>
            <div class="stat-label">Total Timers</div>
          </div>
          <div class="stat-box enabled">
            <div class="stat-value">${enabledTimers}</div>
            <div class="stat-label">Enabled</div>
          </div>
          <div class="stat-box running">
            <div class="stat-value">${runningTimers}</div>
            <div class="stat-label">Running</div>
          </div>
          <div class="stat-box error">
            <div class="stat-value">${errorTimers}</div>
            <div class="stat-label">Errors</div>
          </div>
        </div>

        <h3>📅 Calendar Sync Status</h3>
        <table>
          <tbody>${syncRows}</tbody>
        </table>

        ${errorSection}

        <button class="sync-btn" id="sync-btn">🔄 Sync Calendars Now</button>
      </div>`;

    const syncBtn = this.shadowRoot.getElementById("sync-btn");
    if (syncBtn) {
      syncBtn.addEventListener("click", () => this._triggerSync());
    }
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("atc-status-card", AtcStatusCard);
