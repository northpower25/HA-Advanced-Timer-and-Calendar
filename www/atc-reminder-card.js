/**
 * ATC Reminder Card – Lovelace custom element
 * Displays upcoming reminders sorted by date, color-coded by type.
 */
class AtcReminderCard extends HTMLElement {
  static get properties() {
    return {
      hass: Object,
      config: Object,
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._reminders = [];
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
    const colors = {
      reminder: "#2196F3",
      todo: "#4CAF50",
      anniversary: "#E91E63",
      appointment: "#FF9800",
    };
    return colors[type] || "#9E9E9E";
  }

  _typeIcon(type) {
    const icons = {
      reminder: "🔔",
      todo: "✅",
      anniversary: "🎉",
      appointment: "📅",
    };
    return icons[type] || "📌";
  }

  _formatDate(isoString) {
    if (!isoString || isoString === "unavailable") return "No date";
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  }

  _daysUntil(isoString) {
    if (!isoString) return null;
    const now = Date.now();
    const target = new Date(isoString).getTime();
    const diff = Math.round((target - now) / 86400000);
    return diff;
  }

  _daysLabel(days) {
    if (days === null) return "";
    if (days < 0) return `${Math.abs(days)}d ago`;
    if (days === 0) return "Today";
    if (days === 1) return "Tomorrow";
    return `in ${days}d`;
  }

  _fetchReminders() {
    // Try to get reminder data from the coordinator via calendar entities
    // We use the todo entity states as a proxy indicator
    if (!this._hass) return [];
    const states = this._hass.states;
    const reminders = [];

    // Collect from any ATC-related state attributes that expose reminders
    Object.keys(states).forEach((entityId) => {
      const state = states[entityId];
      if (state.attributes && state.attributes.atc_reminders) {
        state.attributes.atc_reminders.forEach((r) => reminders.push(r));
      }
    });

    return reminders;
  }

  async _completeItem(itemId) {
    if (!this._hass) return;
    await this._hass.callService("advanced_timer_calendar", "complete_todo", {
      reminder_id: itemId,
    });
  }

  render() {
    if (!this.shadowRoot) return;

    const reminders = this._fetchReminders()
      .filter((r) => this._showCompleted || !r.completed)
      .sort((a, b) => {
        const dateA = new Date(a.datetime || a.due_date || a.date || 0).getTime();
        const dateB = new Date(b.datetime || b.due_date || b.date || 0).getTime();
        return dateA - dateB;
      })
      .slice(0, this._maxItems);

    const items = reminders.length === 0
      ? '<li class="empty">No upcoming reminders. Create one using the services.</li>'
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
                    ? `<button class="complete-btn" data-id="${r.id}" title="Complete">✓</button>`
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

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--primary-font-family, sans-serif); }
        .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.12));
          padding: 16px; }
        h2 { margin: 0 0 12px; font-size: 1.1em; color: var(--primary-text-color); }
        ul { list-style: none; margin: 0; padding: 0; }
        .reminder-item { display: flex; align-items: stretch; border-radius: 8px;
          margin-bottom: 8px; overflow: hidden;
          border: 1px solid var(--divider-color, #e0e0e0); transition: background .2s; }
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
        .days-label { font-size: 0.75em; font-weight: 600;
          padding: 1px 6px; border-radius: 10px;
          background: var(--primary-color, #03a9f4); color: white; }
        .overdue .days-label { background: #f44336; }
        .urgent .days-label { background: #FF9800; }
        .type-badge { font-size: 0.7em; padding: 1px 5px; border-radius: 8px; color: white; }
        .complete-btn { border: none; background: none; cursor: pointer; font-size: 1em;
          color: #4CAF50; padding: 0 4px; }
        .empty { text-align: center; color: var(--secondary-text-color); padding: 16px; }
      </style>
      <div class="card">
        <h2>${this._title}</h2>
        <ul>${items}</ul>
      </div>`;

    this.shadowRoot.querySelectorAll(".complete-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const itemId = e.target.dataset.id;
        await this._completeItem(itemId);
      });
    });
  }

  getCardSize() {
    return Math.max(2, Math.min(this._maxItems, 5) + 1);
  }
}

customElements.define("atc-reminder-card", AtcReminderCard);
