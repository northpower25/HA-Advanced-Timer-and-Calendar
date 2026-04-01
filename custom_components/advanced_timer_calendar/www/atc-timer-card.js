/**
 * ATC Timer Card – Lovelace custom element
 * Displays ATC timers with status, next run countdown, control buttons,
 * and modal forms to create, edit and delete timers from the dashboard.
 * Includes entity pickers for Actions and Conditions per the ATC concept.
 */
class AtcTimerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._timers = [];
    this._updateInterval = null;
    this._modal = null; // null | "create" | "edit"
    this._editTimerData = null;
    this._actions = [];
    this._conditions = [];
    this._condLogic = "and";
  }

  setConfig(config) {
    this.config = config || {};
    this._title = this.config.title || "ATC Timers";
  }

  set hass(hass) {
    this._hass = hass;
    this._updateTimers();
    if (!this._modal) {
      this.render();
    }
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
        // Use timer_id UUID from attributes (exposed by switch.py); fall back to slug
        const entitySlug = entityId.replace("switch.", "");
        const timerId = (state.attributes && state.attributes.timer_id) || entitySlug;
        const nextRunEntity = Object.keys(states).find(
          (id) => id.includes(entitySlug) && id.includes("next_run")
        );
        const lastRunEntity = Object.keys(states).find(
          (id) => id.includes(entitySlug) && id.includes("last_run")
        );
        const statusEntity = Object.keys(states).find(
          (id) => id.includes(entitySlug) && id.includes("_status")
        );
        this._timers.push({
          entityId,
          timerId,
          name: state.attributes.friendly_name || entityId,
          enabled: state.state === "on",
          nextRun: nextRunEntity ? states[nextRunEntity].state : null,
          lastRun: lastRunEntity ? states[lastRunEntity].state : null,
          status: statusEntity ? states[statusEntity].state : "idle",
          attrs: state.attributes || {},
        });
      }
    });
  }

  _formatCountdown(isoString) {
    if (!isoString || isoString === "unavailable" || isoString === "unknown") return "–";
    const diff = new Date(isoString).getTime() - Date.now();
    if (diff <= 0) return "now";
    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  _formatDateTime(isoString) {
    if (!isoString || isoString === "unavailable" || isoString === "unknown") return "–";
    try { return new Date(isoString).toLocaleString(); } catch { return isoString; }
  }

  _statusIcon(status) {
    return { idle: "⏸", running: "▶️", paused: "⏸️", skipped: "⏭", error: "❌" }[status] || "⏸";
  }

  async _callService(domain, service, serviceData) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, serviceData);
    } catch (err) {
      alert(`Fehler / Error (${service}): ${err.message || err}`);
    }
  }

  async _toggleTimer(entityId, currentlyEnabled) {
    await this._callService("switch", currentlyEnabled ? "turn_off" : "turn_on", { entity_id: entityId });
  }

  async _runNow(timerId) {
    await this._callService("advanced_timer_calendar", "run_now", { timer_id: timerId });
  }

  async _skipNext(timerId) {
    await this._callService("advanced_timer_calendar", "skip_next", { timer_id: timerId });
  }

  async _deleteTimer(timerId, name) {
    if (!confirm(`Timer "${name}" wirklich löschen?\nDelete timer "${name}"?`)) return;
    await this._callService("advanced_timer_calendar", "delete_timer", { timer_id: timerId });
  }

  _openCreateModal() {
    this._modal = "create";
    this._editTimerData = null;
    this._actions = [];
    this._conditions = [];
    this._condLogic = "and";
    this.render();
  }

  _openEditModal(timer) {
    this._modal = "edit";
    this._editTimerData = timer;
    this._actions = Array.isArray(timer.attrs?.actions) ? JSON.parse(JSON.stringify(timer.attrs.actions)) : [];
    this._conditions = Array.isArray(timer.attrs?.conditions) ? JSON.parse(JSON.stringify(timer.attrs.conditions)) : [];
    // Extract logic from first condition if present
    this._condLogic = (this._conditions.length > 0 && this._conditions[0].logic) ? this._conditions[0].logic : "and";
    this.render();
  }

  _closeModal() {
    this._modal = null;
    this._editTimerData = null;
    this._actions = [];
    this._conditions = [];
    this.render();
  }

  // ── Entity datalist helpers ──────────────────────────────────────────────

  _getEntityDatalistOptions() {
    if (!this._hass) return "";
    return Object.keys(this._hass.states)
      .sort()
      .map((id) => `<option value="${id}"></option>`)
      .join("");
  }

  // ── Action row HTML ──────────────────────────────────────────────────────

  _buildActionRowHTML(action, idx) {
    const entOpts = this._getEntityDatalistOptions();
    const selectedAction = action.action || "turn_on";
    return `
      <div class="action-row" data-idx="${idx}">
        <datalist id="dl-a${idx}">${entOpts}</datalist>
        <input type="text" name="action-entity" list="dl-a${idx}"
          value="${(action.entity_id || "").replace(/"/g, "&quot;")}"
          placeholder="entity_id (z.B. switch.lamp_1)"/>
        <div class="row-inline">
          <select name="action-type">
            ${["turn_on", "turn_off", "toggle"].map((a) =>
              `<option value="${a}" ${selectedAction === a ? "selected" : ""}>${a}</option>`
            ).join("")}
          </select>
          <input type="number" name="action-delay" min="0"
            value="${action.delay_seconds || ""}" placeholder="Delay s" class="narrow-input"/>
          <input type="number" name="action-duration" min="0"
            value="${action.duration_seconds || ""}" placeholder="Dauer s" class="narrow-input"/>
          <button type="button" class="btn btn-rm rm-action" data-idx="${idx}" title="Entfernen / Remove">✕</button>
        </div>
      </div>`;
  }

  // ── Condition row HTML ───────────────────────────────────────────────────

  _buildConditionRowHTML(cond, idx) {
    const entOpts = this._getEntityDatalistOptions();
    const isNumeric = cond.type === "numeric_state";
    return `
      <div class="condition-row" data-idx="${idx}">
        <datalist id="dl-c${idx}">${entOpts}</datalist>
        <input type="text" name="cond-entity" list="dl-c${idx}"
          value="${(cond.entity_id || "").replace(/"/g, "&quot;")}"
          placeholder="entity_id (z.B. sensor.rain)"/>
        <div class="row-inline">
          <select name="cond-type" data-idx="${idx}">
            <option value="state" ${!isNumeric ? "selected" : ""}>state</option>
            <option value="numeric_state" ${isNumeric ? "selected" : ""}>numeric_state</option>
          </select>
          <span class="cond-state-grp" style="${isNumeric ? "display:none" : "display:inline-flex"}">
            <input type="text" name="cond-state"
              value="${(cond.state || "").replace(/"/g, "&quot;")}"
              placeholder="Zustand (z.B. on)" class="medium-input"/>
          </span>
          <span class="cond-numeric-grp" style="${isNumeric ? "display:inline-flex" : "display:none"};gap:4px">
            <input type="number" name="cond-above"
              value="${cond.above != null ? cond.above : ""}" placeholder="über/above" class="narrow-input"/>
            <input type="number" name="cond-below"
              value="${cond.below != null ? cond.below : ""}" placeholder="unter/below" class="narrow-input"/>
          </span>
          <button type="button" class="btn btn-rm rm-condition" data-idx="${idx}" title="Entfernen / Remove">✕</button>
        </div>
      </div>`;
  }

  // ── DOM rebuild helpers (called without full re-render) ──────────────────

  _rebuildActionsDOM() {
    const container = this.shadowRoot.getElementById("actions-list");
    if (!container) return;
    container.innerHTML = this._actions.map((a, i) => this._buildActionRowHTML(a, i)).join("");
    this._attachDynamicListeners();
  }

  _rebuildConditionsDOM() {
    const container = this.shadowRoot.getElementById("conditions-list");
    if (!container) return;
    container.innerHTML = this._conditions.map((c, i) => this._buildConditionRowHTML(c, i)).join("");
    this._attachDynamicListeners();
  }

  // ── Read current DOM values into arrays ─────────────────────────────────

  _readActionsFromDOM() {
    const actions = [];
    this.shadowRoot.querySelectorAll(".action-row").forEach((row) => {
      actions.push({
        entity_id: row.querySelector("[name='action-entity']")?.value?.trim() || "",
        action: row.querySelector("[name='action-type']")?.value || "turn_on",
        delay_seconds: parseInt(row.querySelector("[name='action-delay']")?.value || "0", 10) || 0,
        duration_seconds: parseInt(row.querySelector("[name='action-duration']")?.value || "0", 10) || 0,
      });
    });
    return actions;
  }

  _readConditionsFromDOM() {
    const conditions = [];
    this.shadowRoot.querySelectorAll(".condition-row").forEach((row) => {
      const type = row.querySelector("[name='cond-type']")?.value || "state";
      const cond = {
        entity_id: row.querySelector("[name='cond-entity']")?.value?.trim() || "",
        type,
      };
      if (type === "numeric_state") {
        const above = row.querySelector("[name='cond-above']")?.value;
        const below = row.querySelector("[name='cond-below']")?.value;
        const aboveNum = parseFloat(above);
        const belowNum = parseFloat(below);
        if (!isNaN(aboveNum)) cond.above = aboveNum;
        if (!isNaN(belowNum)) cond.below = belowNum;
      } else {
        cond.state = row.querySelector("[name='cond-state']")?.value?.trim() || "";
      }
      conditions.push(cond);
    });
    return conditions;
  }

  // ── Attach listeners for dynamically created rows ────────────────────────

  _attachDynamicListeners() {
    // Remove-action buttons
    this.shadowRoot.querySelectorAll(".rm-action").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        this._actions = this._readActionsFromDOM();
        const idx = parseInt(e.currentTarget.dataset.idx, 10);
        this._actions.splice(idx, 1);
        this._rebuildActionsDOM();
      });
    });
    // Remove-condition buttons
    this.shadowRoot.querySelectorAll(".rm-condition").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        this._conditions = this._readConditionsFromDOM();
        const idx = parseInt(e.currentTarget.dataset.idx, 10);
        this._conditions.splice(idx, 1);
        this._rebuildConditionsDOM();
      });
    });
    // Condition type toggle (state ↔ numeric_state)
    this.shadowRoot.querySelectorAll("[name='cond-type']").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        const row = e.target.closest(".condition-row");
        if (!row) return;
        const isNumeric = e.target.value === "numeric_state";
        const stateGrp = row.querySelector(".cond-state-grp");
        const numGrp = row.querySelector(".cond-numeric-grp");
        if (stateGrp) stateGrp.style.display = isNumeric ? "none" : "inline-flex";
        if (numGrp) numGrp.style.display = isNumeric ? "inline-flex" : "none";
      });
    });
  }

  async _submitForm() {
    const sr = this.shadowRoot;
    const name = sr.querySelector("[name='name']").value.trim();
    if (!name) { alert("Name ist erforderlich / Name is required"); return; }

    const scheduleType = sr.querySelector("[name='schedule_type']").value;
    const enabled = sr.querySelector("[name='enabled']").checked;
    const data = { name, schedule_type: scheduleType, enabled };

    const timeEl = sr.querySelector("[name='time']");
    if (timeEl && timeEl.value) data.time = timeEl.value;

    const dtEl = sr.querySelector("[name='datetime']");
    if (dtEl && dtEl.value) data.datetime = dtEl.value;

    const intervalEl = sr.querySelector("[name='interval']");
    if (intervalEl && intervalEl.value) data.interval = parseInt(intervalEl.value, 10);

    const unitEl = sr.querySelector("[name='interval_unit']");
    if (unitEl && unitEl.value) data.interval_unit = unitEl.value;

    const cronEl = sr.querySelector("[name='cron']");
    if (cronEl && cronEl.value) data.cron = cronEl.value;

    const sunEl = sr.querySelector("[name='sun_event']");
    if (sunEl && sunEl.value) data.sun_event = sunEl.value;

    const sunOffEl = sr.querySelector("[name='sun_offset_minutes']");
    if (sunOffEl && sunOffEl.value !== "") data.sun_offset_minutes = parseInt(sunOffEl.value, 10);

    // Collect actions (filter out blank entity_id)
    data.actions = this._readActionsFromDOM().filter((a) => a.entity_id);

    // Collect conditions with logic
    const condLogicEl = sr.querySelector("[name='cond-logic']");
    const condLogic = condLogicEl ? condLogicEl.value : "and";
    data.conditions = this._readConditionsFromDOM()
      .filter((c) => c.entity_id)
      .map((c) => ({ ...c, logic: condLogic }));

    if (this._modal === "edit" && this._editTimerData) {
      data.timer_id = this._editTimerData.timerId;
      await this._callService("advanced_timer_calendar", "update_timer", data);
    } else {
      await this._callService("advanced_timer_calendar", "create_timer", data);
    }
    this._closeModal();
  }

  _updateScheduleGroups(scheduleType) {
    const groupMap = {
      once: ["grp-datetime"],
      daily: ["grp-time"],
      weekdays: ["grp-time"],
      yearly: ["grp-time"],
      interval: ["grp-interval"],
      cron: ["grp-cron"],
      sun: ["grp-sun", "grp-sun-offset"],
    };
    const show = groupMap[scheduleType] || [];
    ["grp-time", "grp-datetime", "grp-interval", "grp-cron", "grp-sun", "grp-sun-offset"].forEach((id) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.style.display = show.includes(id) ? "flex" : "none";
    });
  }

  render() {
    if (!this.shadowRoot) return;

    const timers = this._timers;
    const t = this._editTimerData;
    const isEdit = this._modal === "edit";

    const rows = timers.length === 0
      ? '<tr><td colspan="6" class="empty">Keine ATC-Timer vorhanden / No ATC timers found.</td></tr>'
      : timers.map((timer, idx) => {
          const countdown = this._formatCountdown(timer.nextRun);
          const switchId = `sw-${timer.entityId.replace(/\./g, "-")}`;
          return `
            <tr class="timer-row ${timer.status}">
              <td class="name">${timer.name}</td>
              <td class="status">${this._statusIcon(timer.status)} ${timer.status}</td>
              <td class="next-run" title="${timer.nextRun || ""}">
                ${countdown}<br/><small>${this._formatDateTime(timer.nextRun)}</small>
              </td>
              <td class="last-run"><small>${this._formatDateTime(timer.lastRun)}</small></td>
              <td class="actions">
                <label class="toggle">
                  <input type="checkbox" id="${switchId}" ${timer.enabled ? "checked" : ""}
                    data-entity="${timer.entityId}" data-enabled="${timer.enabled}"/>
                  <span class="slider"></span>
                </label>
                <button class="btn run" data-id="${timer.timerId}" title="Jetzt ausführen / Run Now">▶</button>
                <button class="btn skip" data-id="${timer.timerId}" title="Überspringen / Skip Next">⏭</button>
                <button class="btn edit" data-idx="${idx}" title="Bearbeiten / Edit">✏️</button>
                <button class="btn del" data-id="${timer.timerId}" data-name="${timer.name.replace(/"/g, "&quot;")}" title="Löschen / Delete">🗑</button>
              </td>
            </tr>`;
        }).join("");

    const schedType = (t && t.attrs && t.attrs.schedule_type) || "daily";
    const condLogicVal = this._condLogic || "and";

    // Pre-render actions and conditions HTML
    const actionsHTML = this._actions.map((a, i) => this._buildActionRowHTML(a, i)).join("");
    const conditionsHTML = this._conditions.map((c, i) => this._buildConditionRowHTML(c, i)).join("");

    const modalHtml = this._modal ? `
      <div class="modal-overlay" id="modal-overlay">
        <div class="modal">
          <div class="modal-header">
            <h3>${isEdit ? "Timer bearbeiten / Edit Timer" : "Timer erstellen / Create Timer"}</h3>
            <button class="close-btn" id="modal-close">×</button>
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>Name *</label>
              <input type="text" name="name" value="${isEdit && t ? t.name.replace(/"/g, "&quot;") : ""}" placeholder="z.B. Morgen-Licht / Morning Light" required/>
            </div>
            <div class="form-row">
              <label>Zeitplan / Schedule Type</label>
              <select name="schedule_type" id="sched-sel">
                ${["once","daily","weekdays","interval","yearly","cron","sun"].map(st =>
                  `<option value="${st}" ${schedType === st ? "selected" : ""}>${st}</option>`).join("")}
              </select>
            </div>
            <div class="form-row" id="grp-time">
              <label>Uhrzeit / Time (HH:MM)</label>
              <input type="text" name="time" value="${(t && t.attrs && t.attrs.time) || ""}" placeholder="08:00"/>
            </div>
            <div class="form-row" id="grp-datetime">
              <label>Datum &amp; Zeit / Date &amp; Time</label>
              <input type="datetime-local" name="datetime" value="${(t && t.attrs && t.attrs.datetime) ? t.attrs.datetime.slice(0,16) : ""}"/>
            </div>
            <div class="form-row" id="grp-interval">
              <label>Intervall / Interval</label>
              <div style="display:flex;gap:8px">
                <input type="number" name="interval" value="${(t && t.attrs && t.attrs.interval) || ""}" min="1" placeholder="7" style="flex:1"/>
                <select name="interval_unit" style="flex:1">
                  ${["days","weeks","months"].map(u =>
                    `<option value="${u}" ${((t && t.attrs && t.attrs.interval_unit) || "days") === u ? "selected" : ""}>${u}</option>`).join("")}
                </select>
              </div>
            </div>
            <div class="form-row" id="grp-cron">
              <label>Cron-Ausdruck / Cron Expression</label>
              <input type="text" name="cron" value="${(t && t.attrs && t.attrs.cron) || ""}" placeholder="0 8 * * 1-5"/>
            </div>
            <div class="form-row" id="grp-sun">
              <label>Sonnenereignis / Sun Event</label>
              <select name="sun_event">
                ${["sunrise","sunset"].map(se =>
                  `<option value="${se}" ${((t && t.attrs && t.attrs.sun_event) || "sunrise") === se ? "selected" : ""}>${se}</option>`).join("")}
              </select>
            </div>
            <div class="form-row" id="grp-sun-offset">
              <label>Offset Minuten / Offset Minutes</label>
              <input type="number" name="sun_offset_minutes" value="${(t && t.attrs && t.attrs.sun_offset_minutes != null) ? t.attrs.sun_offset_minutes : 0}" min="-240" max="240"/>
            </div>
            <div class="form-row">
              <label class="check-label">
                <input type="checkbox" name="enabled" ${(!isEdit || (t && t.enabled)) ? "checked" : ""}/>
                Aktiviert / Enabled
              </label>
            </div>

            <!-- Actions Section -->
            <div class="form-section">
              <div class="section-hdr">
                <label>⚡ Aktionen / Actions</label>
                <button type="button" class="btn add-item" id="add-action-btn">+ Aktion / Action</button>
              </div>
              <div class="section-hint">Welche Entitäten sollen beim Timer-Auslösen geschaltet werden? / Which entities should be switched when the timer fires?</div>
              <div id="actions-list">${actionsHTML}</div>
            </div>

            <!-- Conditions Section -->
            <div class="form-section">
              <div class="section-hdr">
                <label>🔀 Bedingungen / Conditions</label>
                <div style="display:flex;gap:8px;align-items:center">
                  <select name="cond-logic" style="padding:4px 6px;border:1px solid var(--divider-color,#444);border-radius:4px;background:var(--secondary-background-color,#2a2a2a);color:var(--primary-text-color);font-size:0.85em">
                    <option value="and" ${condLogicVal === "and" ? "selected" : ""}>AND (alle)</option>
                    <option value="or" ${condLogicVal === "or" ? "selected" : ""}>OR (eine)</option>
                  </select>
                  <button type="button" class="btn add-item" id="add-cond-btn">+ Bedingung</button>
                </div>
              </div>
              <div class="section-hint">Timer nur ausführen wenn diese Bedingungen erfüllt sind. / Only fire when these conditions are met.</div>
              <div id="conditions-list">${conditionsHTML}</div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn cancel" id="modal-cancel">Abbrechen / Cancel</button>
            <button class="btn submit" id="modal-submit">${isEdit ? "Speichern / Save" : "Erstellen / Create"}</button>
          </div>
        </div>
      </div>` : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12));
          padding: 16px; overflow: auto; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        h2 { margin: 0; font-size: 1.1em; color: var(--primary-text-color); }
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
        .btn.edit { background: #607d8b; font-size: 0.9em; }
        .btn.del { background: #f44336; font-size: 0.9em; }
        .btn.create { background: #4CAF50; padding: 6px 14px; font-size: 0.9em; }
        .btn.cancel { background: #9e9e9e; }
        .btn.submit { background: var(--primary-color, #03a9f4); }
        .btn.add-item { background: #4CAF50; padding: 3px 8px; font-size: 0.8em; margin-left: 0; }
        .btn.btn-rm { background: #f44336; padding: 2px 6px; font-size: 0.8em; }
        .toggle { position: relative; display: inline-block; width: 34px; height: 20px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
          background: #ccc; border-radius: 20px; transition: .3s; }
        .slider:before { position: absolute; content: ""; height: 14px; width: 14px;
          left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .3s; }
        input:checked + .slider { background: var(--primary-color, #03a9f4); }
        input:checked + .slider:before { transform: translateX(14px); }
        /* Modal */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 9999;
          display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box; }
        .modal { background: var(--card-background-color, #1c1c1c); border-radius: 12px;
          min-width: 300px; max-width: 520px; width: 100%; max-height: 90vh; overflow-y: auto;
          box-shadow: 0 8px 32px rgba(0,0,0,.4); }
        .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--divider-color, #333); }
        .modal-header h3 { margin: 0; font-size: 1em; color: var(--primary-text-color); }
        .close-btn { background: none; border: none; font-size: 1.5em; cursor: pointer; color: var(--secondary-text-color); line-height: 1; padding: 0 4px; }
        .modal-body { padding: 16px; }
        .modal-footer { padding: 8px 16px 16px; display: flex; justify-content: flex-end; gap: 8px; }
        .form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
        .form-row label { font-size: 0.85em; color: var(--secondary-text-color); font-weight: 500; }
        .form-row input[type="text"],.form-row input[type="number"],.form-row input[type="datetime-local"],.form-row select {
          padding: 7px 10px; border: 1px solid var(--divider-color, #444);
          border-radius: 6px; background: var(--secondary-background-color, #2a2a2a);
          color: var(--primary-text-color); font-size: 0.9em; box-sizing: border-box; width: 100%; }
        .check-label { display: flex !important; flex-direction: row !important; align-items: center; gap: 8px; cursor: pointer; font-size: 0.9em !important; color: var(--primary-text-color) !important; }
        .check-label input { width: auto; }
        /* Actions & Conditions */
        .form-section { border-top: 1px solid var(--divider-color, #444); padding-top: 10px; margin-top: 4px; }
        .section-hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
        .section-hdr label { font-size: 0.85em; font-weight: 600; color: var(--secondary-text-color); }
        .section-hint { font-size: 0.78em; color: var(--secondary-text-color); margin-bottom: 8px; }
        .action-row, .condition-row { background: var(--secondary-background-color, #2a2a2a);
          border-radius: 6px; padding: 8px; margin-bottom: 6px; display: flex; flex-direction: column; gap: 6px; }
        .action-row input[type="text"], .action-row input[type="number"],
        .condition-row input[type="text"], .condition-row input[type="number"] {
          padding: 5px 8px; border: 1px solid var(--divider-color, #555);
          border-radius: 4px; background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color); font-size: 0.85em; }
        .action-row select, .condition-row select {
          padding: 5px 8px; border: 1px solid var(--divider-color, #555);
          border-radius: 4px; background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color); font-size: 0.85em; }
        .row-inline { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
        .narrow-input { width: 70px !important; }
        .medium-input { width: 110px !important; }
        .cond-state-grp, .cond-numeric-grp { display: inline-flex; gap: 4px; align-items: center; }
      </style>
      <div class="card">
        <div class="card-header">
          <h2>${this._title}</h2>
          <button class="btn create" id="btn-create">➕ Erstellen / Create</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Name</th><th>Status</th><th>Next Run</th><th>Last Run</th><th>Aktionen / Actions</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${modalHtml}`;

    // Card events
    const createBtn = this.shadowRoot.getElementById("btn-create");
    if (createBtn) createBtn.addEventListener("click", () => this._openCreateModal());

    this.shadowRoot.querySelectorAll(".toggle input").forEach((cb) => {
      cb.addEventListener("change", async (e) => {
        await this._toggleTimer(e.target.dataset.entity, e.target.dataset.enabled === "true");
      });
    });
    this.shadowRoot.querySelectorAll(".btn.run").forEach((btn) => {
      btn.addEventListener("click", async (e) => await this._runNow(e.target.dataset.id));
    });
    this.shadowRoot.querySelectorAll(".btn.skip").forEach((btn) => {
      btn.addEventListener("click", async (e) => await this._skipNext(e.target.dataset.id));
    });
    this.shadowRoot.querySelectorAll(".btn.edit").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = parseInt(e.target.dataset.idx, 10);
        this._openEditModal(this._timers[idx]);
      });
    });
    this.shadowRoot.querySelectorAll(".btn.del").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        await this._deleteTimer(e.target.dataset.id, e.target.dataset.name);
      });
    });

    // Modal events
    if (this._modal) {
      const closeBtn = this.shadowRoot.getElementById("modal-close");
      const cancelBtn = this.shadowRoot.getElementById("modal-cancel");
      const submitBtn = this.shadowRoot.getElementById("modal-submit");
      const overlay = this.shadowRoot.getElementById("modal-overlay");
      const schedSel = this.shadowRoot.getElementById("sched-sel");

      if (closeBtn) closeBtn.addEventListener("click", () => this._closeModal());
      if (cancelBtn) cancelBtn.addEventListener("click", () => this._closeModal());
      if (submitBtn) submitBtn.addEventListener("click", () => this._submitForm());
      if (overlay) overlay.addEventListener("click", (e) => { if (e.target === overlay) this._closeModal(); });
      if (schedSel) {
        this._updateScheduleGroups(schedSel.value);
        schedSel.addEventListener("change", (e) => this._updateScheduleGroups(e.target.value));
      }

      // Add action/condition buttons
      const addActionBtn = this.shadowRoot.getElementById("add-action-btn");
      if (addActionBtn) addActionBtn.addEventListener("click", () => {
        this._actions = this._readActionsFromDOM();
        this._conditions = this._readConditionsFromDOM();
        this._actions.push({ entity_id: "", action: "turn_on", delay_seconds: 0, duration_seconds: 0 });
        this._rebuildActionsDOM();
      });

      const addCondBtn = this.shadowRoot.getElementById("add-cond-btn");
      if (addCondBtn) addCondBtn.addEventListener("click", () => {
        this._actions = this._readActionsFromDOM();
        this._conditions = this._readConditionsFromDOM();
        this._conditions.push({ entity_id: "", type: "state", state: "" });
        this._rebuildConditionsDOM();
      });

      // Attach listeners for pre-rendered action/condition rows
      this._attachDynamicListeners();
    }
  }

  getCardSize() {
    return Math.max(2, this._timers.length + 2);
  }
}

if (!customElements.get("atc-timer-card")) {
  customElements.define("atc-timer-card", AtcTimerCard);
}
