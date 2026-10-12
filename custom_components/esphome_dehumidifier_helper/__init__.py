"""Wrap existing ESPHome entities in a standard HA dehumidifier."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .bindings import sync_entry_sources
from .const import (
    CONF_DEVICE_ID,
    CONF_MODE_NAMES,
    HITACHI_MODE_NAMES,
    HITACHI_MODE_SIGNATURE,
)
from .discovery import device_is_esphome, project_hint

PLATFORMS = (Platform.HUMIDIFIER,)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add new Hitachi defaults without overwriting customized mode names."""
    if entry.version > 2:
        return False
    if entry.version == 2:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    target: dict[str, Any] = options if CONF_MODE_NAMES in options else data
    names = dict(target.get(CONF_MODE_NAMES, {}))
    device = dr.async_get(hass).async_get(data[CONF_DEVICE_ID])
    is_hitachi = (
        device is not None and project_hint(device)
    ) or HITACHI_MODE_SIGNATURE <= names.keys()
    if is_hitachi:
        for option in ("sleep", "purifier"):
            # Version 1 saved an uncustomized unknown mode as its source value.
            if names.get(option) == option:
                names[option] = HITACHI_MODE_NAMES[option]
        target[CONF_MODE_NAMES] = names

    updates: dict[str, Any] = {"version": 2}
    if data != dict(entry.data):
        updates["data"] = data
    if options != dict(entry.options):
        updates["options"] = options
    hass.config_entries.async_update_entry(entry, **updates)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up after ESPHome; unavailable sources recover through events."""
    device = dr.async_get(hass).async_get(entry.data[CONF_DEVICE_ID])
    if device is None or not device_is_esphome(hass, device):
        raise ConfigEntryNotReady("The selected ESPHome device is not registered")
    sync_entry_sources(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entity removal cancels every event subscription."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
