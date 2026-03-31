/**
 * ATC Timer Card – Lovelace custom element
 * Displays ATC timers with status, next run countdown, and control buttons.
 */
class AtcTimerCard extends HTMLElement {
  static get properties() {
    return {
      hass: Object,
      config: Object,
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._timers = [];
    this._updateInterval = null;
  }

  setConfig(config) {
    this.config = config || {};
    this._title = this.config.title || "ATC Timers";
  }

  set hass(hass) {
    this._hass = hass;
    this._updateTimers();
    this.render();
  }

  connectedCallback() {
    this._updateInterval = setInterval(() => this.render(), 30000);
  }

  disconnectedCallback() {
    if (this._updateInterval) {
      clearInterval(this._updateInterval);
      this._updateInterval = null;
    }
  }

  _updateTimers() {
    if (!this._hass) return;
    const states = this._hass.states;
    this._timers = [];

    Object.keys(states).forEach((entityId) => {
      if (entityId.startsWith("switch.") && entityId.includes("atc")) {
        const state = states[entityId];
        const timerId = entityId.replace("switch.", "").replace(/_switch.*/, "");
        const nextRunEntity = Object.keys(states).find(
          (id) => id.includes(timerId) && id.includes("next_run")
        );
        const lastRunEntity = Object.keys(states).find(
          (id) => id.includes(timerId) && id.includes("last_run")
        );
        const statusEntity = Object.keys(states).find(
          (id) => id.includes(timerId) && id.includes("_status")
        );
        this._timers.push({
          entityId,
          name: state.attributes.friendly_name || entityId,
          enabled: state.state === "on",
          nextRun: nextRunEntity ? states[nextRunEntity].state : null,
          lastRun: lastRunEntity ? states[lastRunEntity].state : null,
          status: statusEntity ? states[statusEntity].state : "idle",
        });
      }
    });
  }

  _formatCountdown(isoString) {
    if (!isoString || isoString === "unavailable" || isoString === "unknown") {
      return "–";
    }
    const now = Date.now();
    const target = new Date(isoString).getTime();
    const diff = target - now;
    if (diff <= 0) return "now";
    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  _formatDateTime(isoString) {
    if (!isoString || isoString === "unavailable" || isoString === "unknown") {
      return "–";
    }
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  _statusIcon(status) {
    const icons = {
      idle: "⏸",
      running: "▶️",
      paused: "⏸️",
      skipped: "⏭",
      error: "❌",
    };
    return icons[status] || "⏸";
  }

  async _callService(domain, service, serviceData) {
    if (!this._hass) return;
    await this._hass.callService(domain, service, serviceData);
  }

  async _toggleTimer(entityId, enabled) {
    const action = enabled ? "turn_off" : "turn_on";
    await this._callService("switch", action, { entity_id: entityId });
  }

  async _runNow(timerId) {
    await this._callService("advanced_timer_calendar", "run_now", {
      timer_id: timerId,
    });
  }

  async _skipNext(timerId) {
    await this._callService("advanced_timer_calendar", "skip_next", {
      timer_id: timerId,
    });
  }

  render() {
    if (!this.shadowRoot) return;

    const timers = this._timers;
    const title = this._title;

    const rows = timers.length === 0
      ? '<tr><td colspan="5" class="empty">No ATC timers found. Create one using the services.</td></tr>'
      : timers.map((t) => {
          const countdown = this._formatCountdown(t.nextRun);
          const lastRun = this._formatDateTime(t.lastRun);
          const switchId = `sw-${t.entityId.replace(/\./g, "-")}`;
          return `
            <tr class="timer-row ${t.status}">
              <td class="name">${t.name}</td>
              <td class="status">${this._statusIcon(t.status)} ${t.status}</td>
              <td class="next-run" title="${t.nextRun || ""}">
                ${countdown}<br/><small>${this._formatDateTime(t.nextRun)}</small>
              </td>
              <td class="last-run"><small>${lastRun}</small></td>
              <td class="actions">
                <label class="toggle">
                  <input type="checkbox" id="${switchId}" ${t.enabled ? "checked" : ""}
                    data-entity="${t.entityId}" data-enabled="${t.enabled}"/>
                  <span class="slider"></span>
                </label>
                <button class="btn run" data-id="${t.entityId}" title="Run Now">▶</button>
                <button class="btn skip" data-id="${t.entityId}" title="Skip Next">⏭</button>
              </td>
            </tr>`;
        }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12));
          padding: 16px; overflow: auto; }
        h2 { margin: 0 0 12px; font-size: 1.1em; color: var(--primary-text-color); }
        table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--divider-color, #e0e0e0);
          color: var(--secondary-text-color); font-weight: 600; }
        td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color, #f0f0f0); vertical-align: middle; }
        .name { font-weight: 500; color: var(--primary-text-color); }
        .status { font-size: 0.85em; }
        .next-run small, .last-run small { color: var(--secondary-text-color); font-size: 0.78em; }
        .timer-row.error td { background: rgba(244,67,54,.05); }
        .timer-row.running td { background: rgba(76,175,80,.05); }
        .empty { text-align: center; color: var(--secondary-text-color); padding: 20px; }
        .btn { border: none; border-radius: 4px; padding: 3px 8px; cursor: pointer;
          font-size: 0.85em; margin-left: 2px; background: var(--primary-color, #03a9f4);
          color: white; transition: opacity .2s; }
        .btn:hover { opacity: 0.8; }
        .btn.skip { background: var(--accent-color, #ff9800); }
        .toggle { position: relative; display: inline-block; width: 34px; height: 20px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
          background: #ccc; border-radius: 20px; transition: .3s; }
        .slider:before { position: absolute; content: ""; height: 14px; width: 14px;
          left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .3s; }
        input:checked + .slider { background: var(--primary-color, #03a9f4); }
        input:checked + .slider:before { transform: translateX(14px); }
      </style>
      <div class="card">
        <h2>${title}</h2>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Next Run</th>
              <th>Last Run</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

    // Attach event listeners
    this.shadowRoot.querySelectorAll('.toggle input').forEach((cb) => {
      cb.addEventListener('change', async (e) => {
        const entityId = e.target.dataset.entity;
        const enabled = e.target.dataset.enabled === "true";
        await this._toggleTimer(entityId, enabled);
      });
    });

    this.shadowRoot.querySelectorAll('.btn.run').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const entityId = e.target.dataset.id;
        const timerId = entityId.replace("switch.", "");
        await this._runNow(timerId);
      });
    });

    this.shadowRoot.querySelectorAll('.btn.skip').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const entityId = e.target.dataset.id;
        const timerId = entityId.replace("switch.", "");
        await this._skipNext(timerId);
      });
    });
  }

  getCardSize() {
    return Math.max(2, this._timers.length + 2);
  }
}

customElements.define("atc-timer-card", AtcTimerCard);
