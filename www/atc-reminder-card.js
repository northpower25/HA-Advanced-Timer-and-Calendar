/**
 * ATC Reminder Card – Lovelace custom element
 * Displays upcoming reminders sorted by date, color-coded by type.
 * Includes a modal form to create reminders, todos, appointments and anniversaries.
 */
class AtcReminderCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._reminders = [];
    this._showCreateModal = false;
  }

  setConfig(config) {
    this.config = config || {};
    this._title = this.config.title || "ATC Reminders";
    this._maxItems = this.config.max_items || 10;
    this._showCompleted = this.config.show_completed || false;
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  _typeColor(type) {
    return { reminder: "#2196F3", todo: "#4CAF50", anniversary: "#E91E63", appointment: "#FF9800" }[type] || "#9E9E9E";
  }

  _typeIcon(type) {
    return { reminder: "🔔", todo: "✅", anniversary: "🎉", appointment: "📅" }[type] || "📌";
  }

  _formatDate(isoString) {
    if (!isoString || isoString === "unavailable") return "No date";
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        weekday: "short", year: "numeric", month: "short", day: "numeric",
      });
    } catch { return isoString; }
  }

  _daysUntil(isoString) {
    if (!isoString) return null;
    return Math.round((new Date(isoString).getTime() - Date.now()) / 86400000);
  }

  _daysLabel(days) {
    if (days === null) return "";
    if (days < 0) return `${Math.abs(days)}d ago`;
    if (days === 0) return "Today";
    if (days === 1) return "Tomorrow";
    return `in ${days}d`;
  }

  _fetchReminders() {
    if (!this._hass) return [];
    const states = this._hass.states;
    const reminders = [];
    Object.keys(states).forEach((entityId) => {
      const state = states[entityId];
      if (state.attributes && state.attributes.atc_reminders) {
        state.attributes.atc_reminders.forEach((r) => reminders.push(r));
      }
    });
    return reminders;
  }

  async _callService(domain, service, data) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      alert(`Fehler / Error (${service}): ${err.message || err}`);
    }
  }

  async _completeItem(itemId) {
    await this._callService("advanced_timer_calendar", "complete_todo", { reminder_id: itemId });
  }

  async _submitCreate() {
    const sr = this.shadowRoot;
    const name = sr.querySelector('[name="r-name"]').value.trim();
    if (!name) { alert("Name ist erforderlich / Name is required"); return; }

    const type = sr.querySelector('[name="r-type"]').value;
    const description = sr.querySelector('[name="r-description"]').value.trim();
    const data = { name, type, description };

    if (type === "anniversary") {
      const dateEl = sr.querySelector('[name="r-date"]');
      if (dateEl && dateEl.value) data.date = dateEl.value;
    } else {
      const dtEl = sr.querySelector('[name="r-datetime"]');
      if (dtEl && dtEl.value) data.datetime = dtEl.value;
    }

    await this._callService("advanced_timer_calendar", "create_reminder", data);
    this._showCreateModal = false;
    this.render();
  }

  render() {
    if (!this.shadowRoot) return;

    const reminders = this._fetchReminders()
      .filter((r) => this._showCompleted || !r.completed)
      .sort((a, b) => {
        const da = new Date(a.datetime || a.due_date || a.date || 0).getTime();
        const db = new Date(b.datetime || b.due_date || b.date || 0).getTime();
        return da - db;
      })
      .slice(0, this._maxItems);

    const items = reminders.length === 0
      ? '<li class="empty">Keine Erinnerungen vorhanden / No upcoming reminders.</li>'
      : reminders.map((r) => {
          const dateStr = r.datetime || r.due_date || r.date;
          const days = this._daysUntil(dateStr);
          const daysLabel = this._daysLabel(days);
          const urgent = days !== null && days <= 1 && days >= 0;
          const overdue = days !== null && days < 0;
          const color = this._typeColor(r.type);
          return `
            <li class="reminder-item ${urgent ? "urgent" : ""} ${overdue ? "overdue" : ""} ${r.completed ? "completed" : ""}">
              <span class="type-bar" style="background:${color}"></span>
              <div class="content">
                <div class="name">
                  ${this._typeIcon(r.type)} ${r.name}
                  ${r.type === "todo" && !r.completed
                    ? `<button class="complete-btn" data-id="${r.id}" title="Erledigt / Complete">✓</button>`
                    : ""}
                </div>
                ${r.description ? `<div class="desc">${r.description}</div>` : ""}
                <div class="meta">
                  <span class="date">${this._formatDate(dateStr)}</span>
                  ${daysLabel ? `<span class="days-label">${daysLabel}</span>` : ""}
                  <span class="type-badge" style="background:${color}">${r.type}</span>
                </div>
              </div>
            </li>`;
        }).join("");

    const modalHtml = this._showCreateModal ? `
      <div class="modal-overlay" id="r-modal-overlay">
        <div class="modal">
          <div class="modal-header">
            <h3>Eintrag erstellen / Create Entry</h3>
            <button class="close-btn" id="r-modal-close">×</button>
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>Name *</label>
              <input type="text" name="r-name" placeholder="z.B. Arzttermin / Doctor appointment" required/>
            </div>
            <div class="form-row">
              <label>Typ / Type</label>
              <select name="r-type" id="r-type-sel">
                <option value="reminder">🔔 Erinnerung / Reminder</option>
                <option value="todo">✅ Aufgabe / Todo</option>
                <option value="appointment">📅 Termin / Appointment</option>
                <option value="anniversary">🎉 Jahrestag / Anniversary</option>
              </select>
            </div>
            <div class="form-row" id="r-grp-datetime">
              <label>Datum & Zeit / Date &amp; Time</label>
              <input type="datetime-local" name="r-datetime"/>
            </div>
            <div class="form-row" id="r-grp-date" style="display:none">
              <label>Datum / Date (Jahrestag – nur Monat & Tag werden gespeichert)</label>
              <input type="date" name="r-date"/>
            </div>
            <div class="form-row">
              <label>Beschreibung / Description</label>
              <input type="text" name="r-description" placeholder="Optional"/>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn cancel" id="r-modal-cancel">Abbrechen / Cancel</button>
            <button class="btn submit" id="r-modal-submit">Erstellen / Create</button>
          </div>
        </div>
      </div>` : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12)); padding: 16px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        h2 { margin: 0; font-size: 1.1em; color: var(--primary-text-color); }
        ul { list-style: none; margin: 0; padding: 0; }
        .reminder-item { display: flex; align-items: stretch; border-radius: 8px; margin-bottom: 8px;
          overflow: hidden; border: 1px solid var(--divider-color, #e0e0e0); transition: background .2s; }
        .reminder-item:hover { background: var(--secondary-background-color, #f5f5f5); }
        .reminder-item.urgent { border-color: #FF9800; background: rgba(255,152,0,.05); }
        .reminder-item.overdue { border-color: #f44336; background: rgba(244,67,54,.05); }
        .reminder-item.completed { opacity: 0.5; }
        .type-bar { width: 5px; flex-shrink: 0; }
        .content { padding: 8px 10px; flex: 1; }
        .name { font-weight: 500; color: var(--primary-text-color); font-size: 0.95em;
          display: flex; align-items: center; gap: 6px; }
        .desc { font-size: 0.8em; color: var(--secondary-text-color); margin-top: 2px; }
        .meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; flex-wrap: wrap; }
        .date { font-size: 0.8em; color: var(--secondary-text-color); }
        .days-label { font-size: 0.75em; font-weight: 600; padding: 1px 6px; border-radius: 10px;
          background: var(--primary-color, #03a9f4); color: white; }
        .overdue .days-label { background: #f44336; }
        .urgent .days-label { background: #FF9800; }
        .type-badge { font-size: 0.7em; padding: 1px 5px; border-radius: 8px; color: white; }
        .complete-btn { border: none; background: none; cursor: pointer; font-size: 1em; color: #4CAF50; padding: 0 4px; }
        .empty { text-align: center; color: var(--secondary-text-color); padding: 16px; }
        .btn { border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer;
          font-size: 0.85em; background: var(--primary-color, #03a9f4); color: white; transition: opacity .2s; }
        .btn:hover { opacity: 0.8; }
        .btn.create { background: #4CAF50; padding: 6px 14px; font-size: 0.9em; }
        .btn.cancel { background: #9e9e9e; }
        .btn.submit { background: var(--primary-color, #03a9f4); }
        /* Modal */
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 9999;
          display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box; }
        .modal { background: var(--card-background-color, #1c1c1c); border-radius: 12px;
          min-width: 300px; max-width: 440px; width: 100%; max-height: 90vh; overflow-y: auto;
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
        <div class="card-header">
          <h2>${this._title}</h2>
          <button class="btn create" id="r-btn-create">➕ Erstellen / Create</button>
        </div>
        <ul>${items}</ul>
      </div>
      ${modalHtml}`;

    const createBtn = this.shadowRoot.getElementById("r-btn-create");
    if (createBtn) createBtn.addEventListener("click", () => {
      this._showCreateModal = true;
      this.render();
    });

    this.shadowRoot.querySelectorAll(".complete-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => await this._completeItem(e.target.dataset.id));
    });

    if (this._showCreateModal) {
      const close = this.shadowRoot.getElementById("r-modal-close");
      const cancel = this.shadowRoot.getElementById("r-modal-cancel");
      const submit = this.shadowRoot.getElementById("r-modal-submit");
      const overlay = this.shadowRoot.getElementById("r-modal-overlay");
      const typeSel = this.shadowRoot.getElementById("r-type-sel");

      const closeModal = () => { this._showCreateModal = false; this.render(); };
      if (close) close.addEventListener("click", closeModal);
      if (cancel) cancel.addEventListener("click", closeModal);
      if (overlay) overlay.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });
      if (submit) submit.addEventListener("click", () => this._submitCreate());

      if (typeSel) {
        typeSel.addEventListener("change", (e) => {
          const isAnniversary = e.target.value === "anniversary";
          const dtGrp = this.shadowRoot.getElementById("r-grp-datetime");
          const dGrp = this.shadowRoot.getElementById("r-grp-date");
          if (dtGrp) dtGrp.style.display = isAnniversary ? "none" : "flex";
          if (dGrp) dGrp.style.display = isAnniversary ? "flex" : "none";
        });
      }
    }
  }

  getCardSize() {
    return Math.max(2, Math.min(this._maxItems, 5) + 1);
  }
}

if (!customElements.get("atc-reminder-card")) {
  customElements.define("atc-reminder-card", AtcReminderCard);
}
