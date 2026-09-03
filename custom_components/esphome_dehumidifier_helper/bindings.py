"""Stable source references survive entity_id edits, reloads and restarts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DEVICE_ID,
    CONF_SOURCE_REFS,
    ESPHOME_DOMAIN,
    REQUIRED_ROLES,
    ROLE_DOMAINS,
    ROLES,
)


@callback
def effective_data(entry: ConfigEntry) -> dict[str, Any]:
    """An explicit None in options clears an optional binding."""
    return dict(entry.data) | dict(entry.options)


def _reference(entry: er.RegistryEntry) -> dict[str, str]:
    return {
        "registry_id": entry.id,
        "domain": entry.domain,
        "platform": entry.platform,
        "unique_id": entry.unique_id,
    }


@callback
def resolve_sources(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str | None]:
    """Resolve identities, never reuse an old entity_id for a different entity."""
    registry = er.async_get(hass)
    refs = data.get(CONF_SOURCE_REFS, {})
    result: dict[str, str | None] = {}
    for role in ROLES:
        source: er.RegistryEntry | None = None
        if ref := refs.get(role):
            # The registry UUID survives user edits, including an upstream
            # unique_id migration. The original unique_id is a recovery key.
            source = registry.async_get(ref["registry_id"])
            if source is None:
                entity_id = registry.async_get_entity_id(
                    ref["domain"], ref["platform"], ref["unique_id"]
                )
                source = registry.async_get(entity_id) if entity_id else None
        elif entity_id := data.get(role):
            source = registry.async_get(entity_id)
        if (
            source is not None
            and source.device_id == data[CONF_DEVICE_ID]
            and source.platform == ESPHOME_DOMAIN
            and source.domain in ROLE_DOMAINS[role]
            and source.disabled_by is None
        ):
            result[role] = source.entity_id
        else:
            result[role] = None
    return result


@callback
def validate_sources(
    hass: HomeAssistant, device_id: str, selected: Mapping[str, Any]
) -> dict[str, str]:
    """Validate server-side, including the device boundary and duplicate roles."""
    registry = er.async_get(hass)
    errors: dict[str, str] = {}
    used: set[str] = set()
    for role in ROLES:
        entity_id = selected.get(role)
        if not entity_id:
            if role in REQUIRED_ROLES:
                errors[role] = "required_entity"
            continue
        source = registry.async_get(entity_id)
        if (
            source is None
            or source.device_id != device_id
            or source.platform != ESPHOME_DOMAIN
            or source.domain not in ROLE_DOMAINS[role]
            or source.disabled_by is not None
        ):
            errors[role] = "invalid_entity"
        elif source.id in used:
            errors[role] = "duplicate_entity"
        if source is not None:
            used.add(source.id)
    return errors


@callback
def serialize_sources(
    hass: HomeAssistant, device_id: str, selected: Mapping[str, Any]
) -> dict[str, Any]:
    """Save readable entity IDs plus stable registry identities."""
    registry = er.async_get(hass)
    data: dict[str, Any] = {CONF_DEVICE_ID: device_id, CONF_SOURCE_REFS: {}}
    for role in ROLES:
        data[role] = selected.get(role) or None
        if data[role] and (source := registry.async_get(data[role])):
            data[role] = source.entity_id
            data[CONF_SOURCE_REFS][role] = _reference(source)
    return data


@callback
def sync_entry_sources(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str | None]:
    """Refresh persisted IDs without losing missing sources' recovery keys."""
    current = effective_data(entry)
    resolved = resolve_sources(hass, current)
    changed = dict(current)
    refs = dict(current.get(CONF_SOURCE_REFS, {}))
    registry = er.async_get(hass)
    for role, entity_id in resolved.items():
        if entity_id is not None:
            changed[role] = entity_id
            if source := registry.async_get(entity_id):
                refs[role] = _reference(source)
    changed[CONF_SOURCE_REFS] = refs
    updates: dict[str, Any] = {}
    if dict(entry.data) != changed:
        updates["data"] = changed
    if entry.options:
        options = dict(entry.options)
        options.update({key: changed.get(key) for key in (*ROLES, CONF_SOURCE_REFS)})
        if options != dict(entry.options):
            updates["options"] = options
    if updates:
        hass.config_entries.async_update_entry(entry, **updates)
    return resolved
