"""Wrap existing ESPHome entities in a standard HA dehumidifier."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .bindings import sync_entry_sources
from .const import CONF_DEVICE_ID
from .discovery import device_is_esphome

PLATFORMS = (Platform.HUMIDIFIER,)


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
