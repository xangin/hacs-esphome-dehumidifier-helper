"""Discover ESPHome sources using public registries and the state machine."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_FAN,
    CONF_HUMIDITY,
    CONF_MODE,
    CONF_POWER,
    CONF_TARGET,
    ESPHOME_DOMAIN,
    KNOWN_ESPHOME_PROJECTS,
    REQUIRED_ROLES,
    ROLE_DOMAINS,
    ROLE_NAMES,
    ROLES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Detection:
    """Unambiguous bindings and roles requiring an explicit choice."""

    entities: dict[str, str | None]
    manual_roles: tuple[str, ...]


@callback
def device_is_esphome(hass: HomeAssistant, device: dr.DeviceEntry) -> bool:
    """Confirm ownership, independent of the device's display name."""
    return any(
        (entry := hass.config_entries.async_get_entry(entry_id)) is not None
        and entry.domain == ESPHOME_DOMAIN
        for entry_id in device.config_entries
    )


def device_unique_id(device: dr.DeviceEntry) -> str:
    """Prefer ESPHome identifiers, then registered MAC, then registry UUID.

    Current ESPHome main devices use a network MAC connection rather than an
    identifier. Values are opaque; no name or MAC suffix parsing is involved.
    """
    identifiers = sorted(i for i in device.identifiers if i[0] == ESPHOME_DOMAIN)
    if identifiers:
        return "identifier:" + json.dumps(identifiers[0], separators=(",", ":"))
    connections = sorted(c for c in device.connections if c[0] == dr.CONNECTION_NETWORK_MAC)
    if connections:
        return "connection:" + json.dumps(connections[0], separators=(",", ":"))
    return f"device:{device.id}"


def project_hint(device: dr.DeviceEntry) -> bool:
    """Recognize public metadata, without claiming it is a project-name API.

    ESPHome currently splits project.name into manufacturer/model. These are
    hints only: the registry does not expose the original complete project name.
    """
    return any(
        (device.manufacturer, device.model) == tuple(project.split(".", 1))
        for project in KNOWN_ESPHOME_PROJECTS
    )


@callback
def source_entries(hass: HomeAssistant, device_id: str) -> list[er.RegistryEntry]:
    """Only enabled ESPHome entities on this exact device are eligible."""
    return [
        entry
        for entry in er.async_entries_for_device(er.async_get(hass), device_id)
        if entry.platform == ESPHOME_DOMAIN and entry.disabled_by is None
    ]


@callback
def role_candidates(
    hass: HomeAssistant, device_id: str, role: str
) -> list[er.RegistryEntry]:
    """List sources that can be explicitly selected for a role."""
    return [
        entry
        for entry in source_entries(hass, device_id)
        if entry.domain in ROLE_DOMAINS[role]
    ]


@callback
def _score(hass: HomeAssistant, entry: er.RegistryEntry, role: str) -> int:
    """Rank metadata evidence. Ties must never select an arbitrary entity."""
    state = hass.states.get(entry.entity_id)
    attributes = state.attributes if state is not None else {}
    name = " ".join((entry.original_name or "").split()).casefold()
    named = name in ROLE_NAMES[role]
    percentage = (entry.unit_of_measurement or attributes.get("unit_of_measurement")) == "%"
    if role == CONF_HUMIDITY:
        humidity_class = "humidity" in (
            entry.original_device_class,
            entry.device_class,
            attributes.get("device_class"),
        )
        if humidity_class:
            return 100 + (10 if named else 0) + int(percentage)
        return 50 + int(percentage) if named else 0
    if role == CONF_TARGET:
        return 100 + int(percentage) if named else (30 if percentage else 0)
    if role == CONF_FAN and entry.domain == "fan":
        return 100 if named else 0
    return 100 if named else 0


@callback
def detect_entities(hass: HomeAssistant, device_id: str) -> Detection:
    """Resolve known roles; optional sources may deliberately remain absent."""
    entities: dict[str, str | None] = {}
    manual: list[str] = []
    for role in ROLES:
        candidates = [
            entry
            for entry in role_candidates(hass, device_id, role)
            if entry.entity_category != "diagnostic"
        ]
        ranked = [(entry, _score(hass, entry, role)) for entry in candidates]
        best_score = max((score for _, score in ranked), default=0)
        best = [entry for entry, score in ranked if score == best_score and score > 0]
        if not best and role == CONF_POWER and len(candidates) == 1:
            best = candidates
        entities[role] = best[0].entity_id if len(best) == 1 else None
        if entities[role] is None and (role in REQUIRED_ROLES or candidates):
            manual.append(role)

    # One select cannot serve as both operation mode and fan speed.
    if entities[CONF_MODE] and entities[CONF_MODE] == entities[CONF_FAN]:
        for role in (CONF_MODE, CONF_FAN):
            entities[role] = None
            if role not in manual:
                manual.append(role)
    _LOGGER.debug("Device %s: %s roles need a choice", device_id, len(manual))
    return Detection(entities, tuple(manual))


@callback
def eligible_devices(hass: HomeAssistant) -> list[dr.DeviceEntry]:
    """Prefer project hints; fall back to the switch/sensor/number structure."""
    devices: list[dr.DeviceEntry] = []
    for device in dr.async_get(hass).devices.values():
        if device.disabled_by is not None or not device_is_esphome(hass, device):
            continue
        domains = {entry.domain for entry in source_entries(hass, device.id)}
        if project_hint(device) or {"switch", "sensor", "number"} <= domains:
            devices.append(device)
    return sorted(
        devices,
        key=lambda device: (
            not project_hint(device),
            (device.name_by_user or device.name or "").casefold(),
            device.id,
        ),
    )
