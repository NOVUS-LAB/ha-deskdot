"""DeskDot — MQTT services wrapper for Local MQTT mode."""

from __future__ import annotations

import json
import pathlib
import re
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components import mqtt
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_registry import async_entries_for_device, async_get

from .const import DOMAIN, MQTT_BASE_TOPIC_ENTITY_NAME

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

LOVELACE_CARD_URL = "/deskdot/deskdot-card.js"
LOVELACE_CARD_PATH = pathlib.Path(__file__).parent / "www" / "deskdot-card.js"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

_SERVICE_INTERNAL_KEYS = frozenset({"device", "card_id", "command"})

_CLOCK_VARIANTS = frozenset(
    {"compact", "wide", "weekdays", "time_only", "time_weekdays"}
)
_TRANSITION_STYLES = frozenset(
    {
        "random",
        "wipe_down",
        "wipe_up",
        "slide_left",
        "slide_right",
        "slide_up",
        "slide_down",
        "fade",
    }
)
_NOTIFICATION_SPEEDS = frozenset({"slow", "medium", "fast"})
_CONTROL_COMMANDS = frozenset(
    {"next", "prev", "pause", "resume", "sleep", "wake", "reboot"}
)


async def async_setup(hass: HomeAssistant, _: dict) -> bool:
    """Register DeskDot MQTT services and frontend card."""
    await _register_lovelace_card(hass)

    async def notify(call: ServiceCall) -> None:
        device = call.data.get("device")
        payload = _prepare_notify_payload(call.data)
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/notify", payload)

    async def dismiss_notify(call: ServiceCall) -> None:
        device = call.data.get("device")
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/notify", "")

    async def card(call: ServiceCall) -> None:
        device = call.data.get("device")
        card_id = call.data.get("card_id") or call.data.get("id")
        if not isinstance(card_id, str) or not _SAFE_ID.match(card_id):
            raise HomeAssistantError(
                "card_id must be 1-32 chars of lowercase letters, numbers, "
                "underscore, or dash"
            )
        payload = _prepare_card_payload(call.data, card_id)
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/cards/{card_id}", payload, retain=True)

    async def delete_card(call: ServiceCall) -> None:
        device = call.data.get("device")
        card_id = call.data.get("card_id") or call.data.get("id")
        if not isinstance(card_id, str) or not _SAFE_ID.match(card_id):
            raise HomeAssistantError(
                "card_id must be 1-32 chars of lowercase letters, numbers, "
                "underscore, or dash"
            )
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/cards/{card_id}", "", retain=True)

    async def settings(call: ServiceCall) -> None:
        device = call.data.get("device")
        payload = _prepare_settings_payload(call.data)
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/settings", payload)

    async def control(call: ServiceCall) -> None:
        device = call.data.get("device")
        command = call.data.get("command")
        if command not in _CONTROL_COMMANDS:
            raise HomeAssistantError(
                "command must be one of: "
                + ", ".join(sorted(_CONTROL_COMMANDS))
            )
        payload = json.dumps({"command": command})
        base = await _get_base_topic(hass, device)
        await mqtt.async_publish(hass, f"{base}/control", payload)

    hass.services.async_register(DOMAIN, "notify", notify)
    hass.services.async_register(DOMAIN, "dismiss_notify", dismiss_notify)
    hass.services.async_register(DOMAIN, "card", card)
    hass.services.async_register(DOMAIN, "delete_card", delete_card)
    hass.services.async_register(DOMAIN, "settings", settings)
    hass.services.async_register(DOMAIN, "control", control)

    return True


PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise entry configuration."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _register_lovelace_card(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card JS and register it as a frontend resource."""
    registered_key = f"{DOMAIN}_lovelace_registered"
    if hass.data.get(registered_key):
        return
    hass.data[registered_key] = True

    await hass.http.async_register_static_paths(
        [StaticPathConfig(LOVELACE_CARD_URL, str(LOVELACE_CARD_PATH), cache_headers=False)]
    )
    from homeassistant.components.frontend import add_extra_js_url
    add_extra_js_url(hass, LOVELACE_CARD_URL)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entry after unload component."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _strip_service_keys(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in _SERVICE_INTERNAL_KEYS}


def _normalize_color(value: Any) -> str:
    """Convert HA color_rgb (list/tuple/int) or hex string to #RRGGBB."""
    if isinstance(value, str):
        if _HEX_COLOR.match(value):
            return value.upper()
        raise HomeAssistantError("color must be a #RRGGBB hex string")
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            red, green, blue = (int(channel) for channel in value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("color RGB channels must be integers") from err
        if not all(0 <= channel <= 255 for channel in (red, green, blue)):
            raise HomeAssistantError("color RGB channels must be between 0 and 255")
        return f"#{red:02X}{green:02X}{blue:02X}"
    if isinstance(value, int):
        red = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        blue = value & 0xFF
        return f"#{red:02X}{green:02X}{blue:02X}"
    raise HomeAssistantError("color must be a #RRGGBB hex string or RGB list")


def _prepare_notify_payload(data: dict[str, Any]) -> str:
    payload = _strip_service_keys(data)
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HomeAssistantError("text is required for notify")
    if len(text) > 160:
        raise HomeAssistantError("text must be 160 characters or fewer")

    if "color" in payload:
        payload["color"] = _normalize_color(payload["color"])
    if "speed" in payload and payload["speed"] not in _NOTIFICATION_SPEEDS:
        raise HomeAssistantError("speed must be one of: slow, medium, fast")
    if "plays" in payload:
        plays = payload["plays"]
        if not isinstance(plays, int) or plays < 1 or plays > 10:
            raise HomeAssistantError("plays must be an integer between 1 and 10")
    if "duration" in payload:
        duration = payload["duration"]
        if not isinstance(duration, int) or duration < 1 or duration > 120:
            raise HomeAssistantError("duration must be an integer between 1 and 120")
    if "sound" in payload and not isinstance(payload["sound"], bool):
        raise HomeAssistantError("sound must be a boolean")

    if "pushIcon" in payload:
        push_icon = payload["pushIcon"]
        if isinstance(push_icon, str):
            if push_icon not in {"0", "1", "2"}:
                raise HomeAssistantError("pushIcon must be '0', '1', or '2'")
        elif isinstance(push_icon, int):
            if push_icon not in {0, 1, 2}:
                raise HomeAssistantError("pushIcon must be 0, 1, or 2")
        else:
            raise HomeAssistantError("pushIcon must be 0, 1, or 2")

    if "noScroll" in payload:
        no_scroll = payload["noScroll"]
        if not isinstance(no_scroll, bool):
            raise HomeAssistantError("noScroll must be a boolean")

    return json.dumps(payload)


def _prepare_card_payload(data: dict[str, Any], card_id: str) -> str:
    payload = _strip_service_keys(data)
    payload.pop("id", None)
    payload["id"] = card_id

    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        raise HomeAssistantError("enabled must be a boolean")

    meaningful_keys = {k for k, v in payload.items() if k != "id" and v not in (None, "", [])}
    is_toggle_only = meaningful_keys == {"enabled"} or meaningful_keys == set()
    if "enabled" in payload and is_toggle_only:
        return json.dumps({"id": card_id, "enabled": payload["enabled"]})

    card_type = payload.get("type", "text")
    if card_type not in {"text", "clock", "pixel"}:
        raise HomeAssistantError("type must be 'text', 'clock', or 'pixel'")

    if card_type != "pixel":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HomeAssistantError("text is required for text and clock cards")
        if len(text) > 160:
            raise HomeAssistantError("text must be 160 characters or fewer")

    if "color" in payload:
        payload["color"] = _normalize_color(payload["color"])

    if "duration" in payload:
        duration = payload["duration"]
        if not isinstance(duration, int) or duration < 1 or duration > 120:
            raise HomeAssistantError("duration must be an integer between 1 and 120")
    else:
        payload["duration"] = 10

    if "priority" in payload:
        priority = payload["priority"]
        if not isinstance(priority, int) or priority < 0 or priority > 100:
            raise HomeAssistantError("priority must be an integer between 0 and 100")
    else:
        payload["priority"] = 50

    if "clockVariant" in payload and payload["clockVariant"] not in _CLOCK_VARIANTS:
        raise HomeAssistantError(
            "clockVariant must be one of: " + ", ".join(sorted(_CLOCK_VARIANTS))
        )

    if "pixelPalette" in payload:
        palette = payload["pixelPalette"]
        if not isinstance(palette, list) or not palette:
            raise HomeAssistantError("pixelPalette must be a non-empty list of colours")
        payload["pixelPalette"] = [_normalize_color(item) for item in palette]

    if "pushIcon" in payload:
        push_icon = payload["pushIcon"]
        if isinstance(push_icon, str):
            if push_icon not in {"0", "1", "2"}:
                raise HomeAssistantError("pushIcon must be '0', '1', or '2'")
        elif isinstance(push_icon, int):
            if push_icon not in {0, 1, 2}:
                raise HomeAssistantError("pushIcon must be 0, 1, or 2")
        else:
            raise HomeAssistantError("pushIcon must be 0, 1, or 2")

    if "noScroll" in payload:
        no_scroll = payload["noScroll"]
        if not isinstance(no_scroll, bool):
            raise HomeAssistantError("noScroll must be a boolean")

    if "speed" in payload:
        speed = payload["speed"]
        if isinstance(speed, str):
            if speed not in _NOTIFICATION_SPEEDS:
                raise HomeAssistantError("speed must be one of: slow, medium, fast")
        elif isinstance(speed, int):
            if speed < 15 or speed > 250:
                raise HomeAssistantError("speed must be an integer between 15 and 250")
        else:
            raise HomeAssistantError("speed must be a string or integer")

    if "scrollMsPerPixel" in payload:
        scroll_speed = payload["scrollMsPerPixel"]
        if not isinstance(scroll_speed, int) or scroll_speed < 15 or scroll_speed > 250:
            raise HomeAssistantError("scrollMsPerPixel must be an integer between 15 and 250")

    if "scrollRepeats" in payload:
        repeats = payload["scrollRepeats"]
        if not isinstance(repeats, int) or repeats < 1 or repeats > 10:
            raise HomeAssistantError("scrollRepeats must be an integer between 1 and 10")

    return json.dumps(payload)


def _prepare_settings_payload(data: dict[str, Any]) -> str:
    payload = _strip_service_keys(data)

    # Protocol docs say timezone; firmware MQTT handler expects tz.
    if "timezone" in payload and "tz" not in payload:
        payload["tz"] = payload.pop("timezone")
    elif "timezone" in payload:
        payload.pop("timezone")

    if "brightness" in payload:
        brightness = payload["brightness"]
        if not isinstance(brightness, int) or brightness < 0 or brightness > 255:
            raise HomeAssistantError("brightness must be an integer between 0 and 255")

    if "clockVariant" in payload and payload["clockVariant"] not in _CLOCK_VARIANTS:
        raise HomeAssistantError(
            "clockVariant must be one of: " + ", ".join(sorted(_CLOCK_VARIANTS))
        )

    if (
        "transitionStyle" in payload
        and payload["transitionStyle"] not in _TRANSITION_STYLES
    ):
        raise HomeAssistantError(
            "transitionStyle must be one of: "
            + ", ".join(sorted(_TRANSITION_STYLES))
        )

    if "pinnedCardId" in payload:
        pinned = payload["pinnedCardId"]
        if pinned is None or pinned == "":
            payload["pinnedCardId"] = None
        elif not isinstance(pinned, str) or not _SAFE_ID.match(pinned):
            raise HomeAssistantError("pinnedCardId must be a valid card id or empty")

    for flag in ("nightMode", "clockEnabled", "showIpOnConnect"):
        if flag in payload and not isinstance(payload[flag], bool):
            raise HomeAssistantError(f"{flag} must be a boolean")

    if not payload:
        raise HomeAssistantError("settings requires at least one field")

    return json.dumps(payload)


async def _get_base_topic(hass: HomeAssistant, device_id: str | None) -> str:
    if not device_id:
        raise HomeAssistantError("device is required")

    entity_registry = async_get(hass)
    entities = async_entries_for_device(entity_registry, device_id, True)

    for entity in entities:
        if entity.original_name == MQTT_BASE_TOPIC_ENTITY_NAME:
            state = hass.states.get(entity.entity_id)
            if state is None or not state.state or state.state in {"unknown", "unavailable"}:
                raise HomeAssistantError(
                    "MQTT Base Topic sensor is unavailable; ensure the DeskDot "
                    "is online in Local MQTT mode"
                )
            return state.state.strip().strip("/")

    inferred = _infer_base_topic_from_mqtt(hass, device_id)
    if inferred:
        return inferred

    raise HomeAssistantError(
        "Could not resolve the MQTT base topic for this device. "
        "Confirm the DeskDot is in Local MQTT mode and MQTT discovery entities "
        "are present (or flash firmware that publishes the MQTT Base Topic sensor)."
    )


def _infer_base_topic_from_mqtt(hass: HomeAssistant, device_id: str) -> str | None:
    """Derive {base} from existing discovery topics when Base Topic sensor is absent.

    Firmware publishes entities with topics like `{base}/state` and `{base}/control`.
    """
    try:
        from homeassistant.components.mqtt import debug_info
    except ImportError:
        return None

    try:
        info = debug_info.info_for_device(hass, device_id)
    except Exception:  # noqa: BLE001 - best-effort fallback
        return None

    candidates: list[str] = []
    for entity in info.get("entities", []):
        for subscription in entity.get("subscriptions", []):
            topic = subscription.get("topic")
            if isinstance(topic, str):
                candidates.append(topic)

        discovery = entity.get("discovery_data") or {}
        payload = discovery.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = None
        if isinstance(payload, dict):
            for key in ("stat_t", "state_topic", "cmd_t", "command_topic"):
                topic = payload.get(key)
                if isinstance(topic, str):
                    candidates.append(topic)

        for transmitted in entity.get("transmitted", []):
            topic = transmitted.get("topic")
            if isinstance(topic, str):
                candidates.append(topic)

    suffixes = (
        "/mqtt_base_topic",
        "/settings",
        "/control",
        "/notify",
        "/state",
        "/availability",
        "/manifest",
    )
    for topic in candidates:
        cleaned = topic.strip().strip("/")
        for suffix in suffixes:
            if cleaned.endswith(suffix):
                base = cleaned[: -len(suffix)].strip("/")
                if base:
                    return base

    return None
