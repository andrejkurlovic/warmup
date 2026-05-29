# Warmup — Home Assistant Integration

A modern, fully async Home Assistant integration for [Warmup](https://www.warmup.co.uk/) underfloor heating thermostats (4IE, 6IE). Configurable entirely through the UI — no YAML required.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

> **Forked from [ha-warmup/warmup](https://github.com/ha-warmup/warmup)** and rewritten to use modern Home Assistant patterns: config flow, `DataUpdateCoordinator`, async aiohttp, and proper sensor entities.

---

## What's new in this fork

The original integration required editing `configuration.yaml` and used a synchronous blocking API client. This fork rewrites the integration from the ground up:

- **GUI setup** — add your Warmup account via Settings → Integrations, no YAML needed
- **Re-authentication flow** — prompts you to log in again if your session expires, without breaking your existing setup
- **Async polling** — uses Home Assistant's shared aiohttp session; no extra Python packages required
- **`DataUpdateCoordinator`** — all thermostats share a single 60-second polling cycle
- **Proper sensor entities** — floor temperature, air temperature, away/comfort/sleep/override temperatures, energy and cost are now real HA sensor entities with device classes, state classes and units — not hidden state attributes
- **Device registry** — each thermostat appears as a named HA device with all its entities grouped together
- **Modern service definition** — `warmup.set_override` uses a `target:` selector so you can pick the thermostat from the UI

---

## Supported devices

| Device | Status |
|--------|--------|
| 4IE    | Full support |
| 6IE    | Works — keep your Wi-Fi SSID ≤ 32 chars and password ≤ 15 chars |

---

## Installation

### HACS (recommended)

1. In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/andrejkurlovic/warmup` as an **Integration**
3. Search for **Warmup** and install it
4. Restart Home Assistant

### Manual

```sh
cd /path/to/your/ha/config

git clone https://github.com/andrejkurlovic/warmup.git /tmp/warmup-fork
rm -rf ./custom_components/warmup
cp -r /tmp/warmup-fork/custom_components/warmup ./custom_components/warmup
rm -rf /tmp/warmup-fork
```

Restart Home Assistant after copying.

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Warmup**
3. Enter your [my.warmup.com](https://my.warmup.com/login) email and password
4. Done — your thermostats appear as devices automatically

Each thermostat is registered as a HA device named after the room. You'll get:

- A **climate** entity to control temperature and mode
- **Sensor** entities for floor temp, air temp, and more (see below)

---

## Entities

### Climate

One per thermostat. Supports:

| Feature | Detail |
|---------|--------|
| HVAC modes | `heat`, `auto`, `off` |
| Preset modes | `home` (programme), `away` (frost protection) |
| Target temperature | 0.5 °C steps |

### Sensors

| Sensor | Enabled by default |
|--------|--------------------|
| Floor temperature | Yes |
| Air temperature | Yes |
| Away temperature | No |
| Comfort temperature | No |
| Sleep temperature | No |
| Override temperature | No |
| Energy | No |
| Cost | No |

Disabled sensors can be enabled per-device in **Settings → Devices & Services → Warmup → [device] → entities**.

---

## Service: `warmup.set_override`

Override the target temperature until a given time.

| Field | Required | Description |
|-------|----------|-------------|
| `target` (entity) | Yes | The climate entity to override |
| `temperature` | Yes | Target temperature in °C (0.5° steps) |
| `until` | No | End time as `HH:MM`. Defaults to 1 hour from now |

Example:

```yaml
service: warmup.set_override
target:
  entity_id: climate.warmup_abc123
data:
  temperature: 22.5
  until: "14:00"
```

---

## Debugging

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.warmup: debug
```

---

## License

Apache 2.0 — see [LICENSE.md](LICENSE.md).

---

## Credits & history

This fork is maintained by [@andrejkurlovic](https://github.com/andrejkurlovic).

The integration originated as [@alex-0103](https://github.com/alex-0103)'s Home Assistant custom component, inspired by [@alyc100](https://github.com/alyc100)'s SmartThings driver. It was developed further by the [ha-warmup](https://github.com/ha-warmup) community — notably [@foxy82](https://github.com/foxy82), [@artmg](https://github.com/artmg), [@rct](https://github.com/rct), [@robchandhok](https://github.com/robchandhok), and [@kkoenen](https://github.com/kkoenen) — before this fork modernised the architecture.

Warmup Plc are not affiliated with or involved in this project. All Warmup trademarks belong to them.
