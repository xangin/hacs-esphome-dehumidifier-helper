"""Consumer-facing device selection, fallback mapping and options."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .bindings import effective_data, resolve_sources, serialize_sources, validate_sources
from .const import (
    CONF_DEVICE_ID,
    CONF_MODE,
    CONF_MODE_NAMES,
    DOMAIN,
    ESPHOME_DOMAIN,
    NAME,
    REQUIRED_ROLES,
    ROLE_DOMAINS,
    ROLES,
)
from .discovery import (
    detect_entities,
    device_is_esphome,
    device_unique_id,
    eligible_devices,
    role_candidates,
)
from .modes import mode_names_schema, source_mode_names, submitted_mode_names


@callback
def _entity_schema(hass: HomeAssistant, device_id: str, roles: Iterable[str]) -> vol.Schema:
    """Restrict choices by domain, integration and exact device membership."""
    schema: dict[Any, Any] = {}
    for role in roles:
        marker = vol.Required(role) if role in REQUIRED_ROLES else vol.Optional(role)
        candidates = [entry.entity_id for entry in role_candidates(hass, device_id, role)]
        if candidates:
            schema[marker] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    filter=selector.EntityFilterSelectorConfig(
                        domain=list(ROLE_DOMAINS[role]), integration=ESPHOME_DOMAIN
                    ),
                    include_entities=candidates,
                )
            )
        else:
            # EntitySelector(include_entities=[]) means unrestricted in HA.
            # An empty select instead makes an absent role impossible to misbind.
            schema[marker] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=[], mode=selector.SelectSelectorMode.DROPDOWN)
            )
    return vol.Schema(schema)


@callback
def _summary(hass: HomeAssistant, selected: Mapping[str, Any]) -> dict[str, str]:
    """Names here are presentation only, never lookup keys."""
    registry = er.async_get(hass)
    result: dict[str, str] = {}
    for role in ROLES:
        entity_id = selected.get(role)
        source = registry.async_get(entity_id) if entity_id else None
        if source is None:
            result[role] = "—"
            continue
        state = hass.states.get(source.entity_id)
        name = source.name or (state.name if state else None) or source.original_name
        result[role] = f"✓ {name or source.entity_id}"
    return result


class ESPHomeDehumidifierConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per source device, with no YAML configuration."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_id: str | None = None
        self._selected: dict[str, str | None] = {}
        self._manual_roles: tuple[str, ...] = ()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ESPHomeDehumidifierOptionsFlow:
        """HA injects config_entry; do not assign the read-only property."""
        return ESPHomeDehumidifierOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose an eligible ESPHome device from a filtered dropdown."""
        candidates = {device.id: device for device in eligible_devices(self.hass)}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            if device_id not in candidates:
                return self.async_abort(reason="device_unavailable")
            device = candidates[device_id]
            await self.async_set_unique_id(device_unique_id(device))
            self._abort_if_unique_id_configured()
            if any(
                entry.data.get(CONF_DEVICE_ID) == device_id
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            ):
                return self.async_abort(reason="already_configured")
            self._device_id = device_id
            detection = detect_entities(self.hass, device_id)
            self._selected = detection.entities
            self._manual_roles = detection.manual_roles
            if self._manual_roles:
                return await self.async_step_manual()
            return await self.async_step_confirm()

        configured = {
            entry.data.get(CONF_DEVICE_ID)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        }
        choices = [
            selector.SelectOptionDict(value=device.id, label=device.name_by_user or device.name or NAME)
            for device in candidates.values()
            if device.id not in configured
        ]
        if not choices:
            return self.async_abort(reason="no_devices")
        # DeviceSelector has no include_devices allow-list in HA 2026.6.0.
        # SelectSelector provides the requested precise device dropdown.
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=choices, mode=selector.SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask only for unresolved roles; optional roles can be left blank."""
        assert self._device_id is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            for role in self._manual_roles:
                self._selected[role] = user_input.get(role) or None
            errors = validate_sources(self.hass, self._device_id, self._selected)
            if not errors:
                return await self.async_step_confirm()
            self._manual_roles = tuple(dict.fromkeys((*self._manual_roles, *errors)))
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                _entity_schema(self.hass, self._device_id, self._manual_roles),
                {key: value for key, value in self._selected.items() if value is not None},
            ),
            errors=errors,
            description_placeholders=_summary(self.hass, self._selected),
        )

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Review detection and optionally edit the selected source's mode names."""
        assert self._device_id is not None
        device = dr.async_get(self.hass).async_get(self._device_id)
        if device is None or device.disabled_by is not None or not device_is_esphome(self.hass, device):
            return self.async_abort(reason="device_unavailable")
        data = serialize_sources(self.hass, self._device_id, self._selected)
        names = source_mode_names(self.hass, data)
        errors: dict[str, str] = {}
        if user_input is not None:
            self._abort_if_unique_id_configured()
            errors = validate_sources(self.hass, self._device_id, self._selected)
            if errors:
                self._manual_roles = tuple(errors)
                return await self.async_step_manual()
            if names:
                submitted, errors = submitted_mode_names(names, user_input)
                if submitted:
                    names = submitted
            if not errors:
                return self.async_create_entry(
                    title=device.name_by_user or device.name or NAME,
                    data=data | {CONF_MODE_NAMES: names},
                )
        return self.async_show_form(
            step_id="confirm",
            data_schema=mode_names_schema(names),
            errors=errors,
            description_placeholders=_summary(self.hass, self._selected),
        )


class ESPHomeDehumidifierOptionsFlow(OptionsFlowWithReload):
    """Correct any source mapping and automatically reload the integration."""

    def __init__(self) -> None:
        self._pending_data: dict[str, Any] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = effective_data(self.config_entry)
        device_id = data[CONF_DEVICE_ID]
        device = dr.async_get(self.hass).async_get(device_id)
        if device is None or not device_is_esphome(self.hass, device):
            return self.async_abort(reason="device_unavailable")
        selected = resolve_sources(self.hass, data)
        errors: dict[str, str] = {}
        if user_input is not None:
            previous_mode = selected.get(CONF_MODE)
            # Omitted optional fields explicitly disable those bindings.
            selected = {role: user_input.get(role) or None for role in ROLES}
            errors = validate_sources(self.hass, device_id, selected)
            if not errors:
                self._pending_data = serialize_sources(self.hass, device_id, selected)
                # Keep names across a rename, but not when choosing another select.
                self._pending_data[CONF_MODE_NAMES] = (
                    data.get(CONF_MODE_NAMES, {})
                    if selected.get(CONF_MODE) and selected[CONF_MODE] == previous_mode
                    else {}
                )
                return await self.async_step_mode_names()
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _entity_schema(self.hass, device_id, ROLES),
                {key: value for key, value in selected.items() if value is not None},
            ),
            errors=errors,
        )

    async def async_step_mode_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Extract editable fields only when the selected mode has options."""
        assert self._pending_data is not None
        data = self._pending_data
        device_id = data[CONF_DEVICE_ID]
        device = dr.async_get(self.hass).async_get(device_id)
        if device is None or device.disabled_by is not None or not device_is_esphome(self.hass, device):
            return self.async_abort(reason="device_unavailable")
        selected = resolve_sources(self.hass, data)
        if validate_sources(self.hass, device_id, selected):
            return await self.async_step_init(selected)
        names = source_mode_names(self.hass, data)
        if not names:
            # Offline optional sources must not block saving power/humidity changes.
            return self.async_create_entry(data=data)
        errors: dict[str, str] = {}
        if user_input is not None:
            submitted, errors = submitted_mode_names(names, user_input)
            if not errors:
                return self.async_create_entry(data=data | {CONF_MODE_NAMES: submitted})
            if submitted:
                names = submitted
        return self.async_show_form(
            step_id="mode_names",
            data_schema=mode_names_schema(names),
            errors=errors,
        )
