# HA DeskDot

Home Assistant custom integration that wraps the DeskDot **Local MQTT** API, the same way [ha-awtrix](https://github.com/MiguelAngelLV/ha-awtrix) wraps Awtrix.

It does **not** talk to DeskDot Cloud or the device HTTP console. Your DeskDot must already be in Local MQTT mode and connected to the same broker as Home Assistant. MQTT discovery then creates the HA device; this integration adds service actions for cards, notifications, settings, and control.

## Prerequisites

1. Home Assistant MQTT integration configured (Mosquitto addon or external broker).
2. DeskDot on the same LAN, Wi-Fi configured.
3. On the DeskDot local console (`http://<device-ip>/`), set **Device Control Mode** to **Local MQTT**:
   - MQTT host = your HA broker IP
   - Port = `1883` (or your TLS port if applicable)
   - Base topic = something unique, e.g. `deskdot/bedroom`
4. Firmware that publishes Home Assistant discovery, including the **MQTT Base Topic** sensor.
5. After reboot, confirm a **DeskDot** device appears under Devices & Services (MQTT).

## Installation

### HACS

Add this repository as a custom repository (Integration), install **DeskDot**, then restart Home Assistant.

### Manual

Copy `custom_components/deskdot` into your Home Assistant `config/custom_components/` folder and restart.

## Configuration

**Settings → Devices & services → Add integration → DeskDot.**

You only need one DeskDot integration instance. Individual displays are selected per action from MQTT-discovered devices (`manufacturer: DeskDot`, `model: DeskDot Display`).

If an action shows **no matching device**, the DeskDot is not in Local MQTT mode or MQTT discovery has not created the device yet.

## Actions

| Action | MQTT topic | Purpose |
|---|---|---|
| `deskdot.notify` | `{base}/notify` | Temporary notification overlay |
| `deskdot.dismiss_notify` | `{base}/notify` (empty) | Clear notification |
| `deskdot.card` | `{base}/cards/{card_id}` | Create/update a loop card |
| `deskdot.delete_card` | `{base}/cards/{card_id}` (empty, retained) | Remove a card |
| `deskdot.settings` | `{base}/settings` | Brightness, clock, night mode, transitions, pin, timezone |
| `deskdot.control` | `{base}/control` | `next`, `prev`, `pause`, `resume`, `sleep`, `wake`, `reboot` |

Brightness, sleep, and next/prev/reboot are also exposed as native MQTT entities from firmware discovery. Use those entities for dashboards; use these actions for automations that need payload flexibility.

### AWTRIX Compatibility

DeskDot supports **AWTRIX-compatible** parameters for seamless migration from ha-awtrix:

- **`pushIcon`**: Controls icon layout. `0` = icon pinned left (text scrolls beside it), `1` = icon scrolls with text.
- **`noScroll`**: When `true`, disables text scrolling entirely.

These parameters work with both `deskdot.notify` and `deskdot.card` actions.

### Example automations

Notify:

```yaml
action: deskdot.notify
data:
  device: YOUR_DEVICE_ID
  text: Front door opened
  icon: sms
  color: "#00AAFF"
  duration: 8
  speed: medium
```

Upsert a card:

```yaml
action: deskdot.card
data:
  device: YOUR_DEVICE_ID
  card_id: ha_temp
  text: "22.4 living room"
  icon: sun
  color: "#FFFFFF"
  duration: 10
  priority: 40
  save: true
```

Card with AWTRIX-compatible icon layout:

```yaml
action: deskdot.card
data:
  device: YOUR_DEVICE_ID
  card_id: weather
  text: "Rain in 42m"
  icon: "2284"
  pushIcon: 0
  noScroll: false
  color: "#00aaff"
  duration: 10
  priority: 50
```

Control:

```yaml
action: deskdot.control
data:
  device: YOUR_DEVICE_ID
  command: next
```

## Local MQTT topics

With base topic `deskdot/bedroom`:

```text
deskdot/bedroom/cards/+
deskdot/bedroom/notify
deskdot/bedroom/settings
deskdot/bedroom/control
deskdot/bedroom/state
deskdot/bedroom/availability
deskdot/bedroom/mqtt_base_topic
```

## Troubleshooting

- **No matching device in action dropdown** — DeskDot must publish MQTT discovery. Check broker retained `homeassistant/+/deskdot_*/+/config` topics and that manufacturer/model are `DeskDot` / `DeskDot Display`.
- **MQTT Base Topic unavailable** — Flash firmware that includes the base-topic discovery sensor, then reconnect MQTT so discovery republishes.
- **Action does nothing** — Confirm `mqtt_base_topic` state matches the base topic configured on the device, and that HA MQTT can publish to `{base}/#`.
