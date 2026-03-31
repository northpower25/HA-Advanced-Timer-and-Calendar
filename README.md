# HA Advanced Timer & Calendar

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.0.0+-blue.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**HA Advanced Timer & Calendar** (ATC) is a powerful Home Assistant custom component that combines flexible scheduling, reminders, to-dos, and external calendar synchronisation in a single integration.

---

## Features

| Feature | Description |
|---|---|
| **Flexible Timers** | Daily, weekday, interval, cron, sunrise/sunset, yearly |
| **Reminders & To-Dos** | One-off reminders with recurrence, anniversaries, appointments |
| **Conditions** | AND/OR condition groups on entity state, numeric values, and templates |
| **Smart Watering** | Adaptive irrigation based on temperature, soil moisture, and weather forecast |
| **Timer Templates** | Ready-made presets for irrigation, lighting, climate, and security |
| **Import / Export** | Backup and restore all timers and reminders as JSON |
| **Statistics** | Execution history and skip-rate analytics per timer |
| **Notifications** | Telegram (Mode A & B), voice (Alexa, Google Cast, Sonos, TTS) |
| **Notification Escalation** | Repeat reminders until acknowledged |
| **External Calendars** | Microsoft 365, Google Calendar, Apple iCloud sync |
| **YAML Export** | Generate equivalent HA automation YAML for any timer |

---

## Installation

### Via HACS (recommended)

1. Open **HACS** in the Home Assistant sidebar.
2. Click **Integrations** → **⋮ (menu)** → **Custom repositories**.
3. Enter the repository URL and select category **Integration**, then click **Add**.
4. Search for **Advanced Timer & Calendar** in HACS and click **Download**.
5. Restart Home Assistant (*Settings → System → Restart*).
6. Go to **Settings → Devices & Services → Add Integration** and search for **Advanced Timer & Calendar**.

### Manual

Copy the `custom_components/advanced_timer_calendar` directory into your Home Assistant `custom_components` folder and restart Home Assistant.

---

## Documentation

| Language | Guide |
|---|---|
| 🇬🇧 English | [User Guide](docs/user_guide.md) |
| 🇩🇪 Deutsch | [Benutzerhandbuch](docs/user_guide_de.md) |
| Developer | [Developer Guide](docs/developer_guide.md) |

The guides cover:

- **Installation & initial setup** – Config Flow walkthrough, entities created
- **Creating timers** – all schedule types with YAML examples (daily, weekday, interval, cron, sunrise/sunset, yearly)
- **Reminders & To-Dos** – one-off, recurring, anniversary
- **Conditions** – entity state, numeric, template, AND/OR groups
- **Notifications** – Telegram Mode A & B, voice providers, escalation
- **Dashboard cards** – timer overview, calendar card, to-do card, button card
- **External calendars** – Microsoft 365, Google Calendar, Apple iCloud setup
- **Services reference** – full list of all HA service calls
- **FAQ & Troubleshooting** – common issues and solutions

---

## Quick Start

```yaml
# Create a daily timer at 07:00 to turn on garden lights for one hour
service: advanced_timer_calendar.create_timer
data:
  name: "Morning Garden Lights"
  schedule_type: daily
  time: "07:00:00"
  enabled: true
  actions:
    - entity_id: light.garden
      service: light.turn_on
      duration_seconds: 3600
```

---

## Requirements

- Home Assistant **2026.0.0** or newer
- [HACS](https://hacs.xyz) (for HACS installation)

---

## Contributing

See the [Developer Guide](docs/developer_guide.md) for architecture details, how to add new schedule types or notification channels, testing guidelines, and the pull request checklist.

---

## License

This project is licensed under the [MIT License](LICENSE).
