"""DeskDot sensor platform — exposes active card inventory per device."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, MANUFACTURER, MODEL, MQTT_BASE_TOPIC_ENTITY_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DeskDot card inventory sensors from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("card_sensors", {})

    from homeassistant.helpers.entity_registry import async_get

    entity_registry = async_get(hass)

    tracked_devices: set[str] = set()

    def _find_base_topic_entities() -> list[tuple[str, str]]:
        """Find all MQTT Base Topic entities and their device IDs."""
        results = []
        for entity in entity_registry.entities.values():
            if (
                entity.original_name == MQTT_BASE_TOPIC_ENTITY_NAME
                and entity.platform == "mqtt"
                and entity.device_id
            ):
                results.append((entity.entity_id, entity.device_id))
        return results

    async def _setup_sensor_for_device(entity_id: str, device_id: str) -> None:
        if device_id in tracked_devices:
            return

        state = hass.states.get(entity_id)
        if not state or not state.state or state.state in {"unknown", "unavailable"}:
            return

        base_topic = state.state.strip().strip("/")
        if not base_topic:
            return

        tracked_devices.add(device_id)
        sensor = DeskDotCardInventorySensor(hass, device_id, base_topic)
        async_add_entities([sensor])
        await sensor.async_subscribe()

    for entity_id, device_id in _find_base_topic_entities():
        await _setup_sensor_for_device(entity_id, device_id)

    @callback
    def _on_state_change(event) -> None:
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in {"unknown", "unavailable", ""}:
            return
        entity_id = event.data.get("entity_id")
        for eid, device_id in _find_base_topic_entities():
            if eid == entity_id:
                hass.async_create_task(_setup_sensor_for_device(eid, device_id))
                break

    base_topic_entity_ids = [eid for eid, _ in _find_base_topic_entities()]
    if base_topic_entity_ids:
        async_track_state_change_event(hass, base_topic_entity_ids, _on_state_change)

    @callback
    def _on_any_state_change(event) -> None:
        new_state = event.data.get("new_state")
        if not new_state:
            return
        entity_id = event.data.get("entity_id")
        if entity_id in base_topic_entity_ids:
            return
        entry_obj = entity_registry.async_get(entity_id)
        if (
            entry_obj
            and entry_obj.original_name == MQTT_BASE_TOPIC_ENTITY_NAME
            and entry_obj.platform == "mqtt"
            and entry_obj.device_id
            and entry_obj.device_id not in tracked_devices
        ):
            base_topic_entity_ids.append(entity_id)
            async_track_state_change_event(hass, [entity_id], _on_state_change)
            hass.async_create_task(
                _setup_sensor_for_device(entity_id, entry_obj.device_id)
            )

    hass.bus.async_listen("state_changed", _on_any_state_change)


class DeskDotCardInventorySensor(SensorEntity):
    """Sensor that maintains an inventory of cards on a DeskDot device."""

    _attr_has_entity_name = True
    _attr_name = "Card Inventory"
    _attr_icon = "mdi:cards-outline"

    def __init__(
        self, hass: HomeAssistant, device_id: str, base_topic: str
    ) -> None:
        self.hass = hass
        self._device_id = device_id
        self._base_topic = base_topic
        self._cards: dict[str, dict[str, Any]] = {}
        self._unsubscribe: Any = None

        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(device_id)
        self._device_identifiers: set[tuple[str, str]] = set()
        if device_entry:
            self._device_identifiers = device_entry.identifiers
            mqtt_id = next(
                (v for domain, v in device_entry.identifiers if domain == "mqtt"),
                None,
            )
            self._attr_unique_id = f"{mqtt_id}_card_inventory" if mqtt_id else f"deskdot_{device_id}_card_inventory"
        else:
            self._attr_unique_id = f"deskdot_{device_id}_card_inventory"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers=self._device_identifiers,
        )

    @property
    def native_value(self) -> int:
        return len(self._cards)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "cards": list(self._cards.values()),
            "card_ids": sorted(self._cards.keys()),
        }

    async def async_subscribe(self) -> None:
        topic = f"{self._base_topic}/cards/+"

        @callback
        def _card_received(msg) -> None:
            parts = msg.topic.rsplit("/", 1)
            if len(parts) < 2:
                return
            card_id = parts[-1]

            if not msg.payload:
                self._cards.pop(card_id, None)
            else:
                try:
                    data = json.loads(msg.payload)
                except (json.JSONDecodeError, TypeError):
                    return
                if isinstance(data, dict):
                    data.setdefault("id", card_id)
                    self._cards[card_id] = data

            self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(
            self.hass, topic, _card_received, qos=0
        )
        _LOGGER.debug("Subscribed to %s for card inventory", topic)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
