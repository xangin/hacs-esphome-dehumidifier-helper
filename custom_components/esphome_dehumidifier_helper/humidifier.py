"""Event-driven standard HumidifierEntity backed exclusively by ESPHome states."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_device_registry_updated_event, async_track_state_change_event

from .bindings import effective_data, resolve_sources, sync_entry_sources
from .const import (
    CONF_DEVICE_ID,
    CONF_HUMIDITY,
    CONF_MODE,
    CONF_POWER,
    CONF_SOURCE_REFS,
    CONF_TARGET,
    DOMAIN,
    REQUIRED_ROLES,
    STATE_ROLES,
)
from .values import humidity_limits, humidity_value, valid_humidity_setting

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create exactly one humidifier per entry."""
    async_add_entities([ESPHomeDehumidifier(hass, entry)])


class ESPHomeDehumidifier(HumidifierEntity):
    """Reflect source states; commands never create an optimistic state."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "dehumidifier"
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._device_id: str = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}:humidifier"
        self._sources = resolve_sources(hass, effective_data(entry))
        self._unsubscribe_states: CALLBACK_TYPE | None = None
        # Same public association mechanism as core switch_as_x: reuse the
        # existing DeviceEntry without rewriting identifiers or manufacturer.
        self.device_entry = dr.async_get(hass).async_get(self._device_id)

    @callback
    def _source_state(self, role: str) -> State | None:
        entity_id = self._sources.get(role)
        return self.hass.states.get(entity_id) if entity_id else None

    @property
    def available(self) -> bool:
        device = dr.async_get(self.hass).async_get(self._device_id)
        if device is None or device.disabled_by is not None:
            return False
        for role in REQUIRED_ROLES:
            state = self._source_state(role)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return False
        return (
            self.is_on is not None
            and self.current_humidity is not None
            and self.target_humidity is not None
        )

    @property
    def is_on(self) -> bool | None:
        state = self._source_state(CONF_POWER)
        if state is None or state.state not in (STATE_ON, STATE_OFF):
            return None
        return state.state == STATE_ON

    @property
    def current_humidity(self) -> float | None:
        state = self._source_state(CONF_HUMIDITY)
        return humidity_value(state.state) if state else None

    @property
    def target_humidity(self) -> float | None:
        state = self._source_state(CONF_TARGET)
        return humidity_value(state.state) if state else None

    @property
    def _target_attributes(self) -> Mapping[str, Any]:
        state = self._source_state(CONF_TARGET)
        return state.attributes if state else {}

    @property
    def min_humidity(self) -> float:
        return humidity_limits(self._target_attributes)[0]

    @property
    def max_humidity(self) -> float:
        return humidity_limits(self._target_attributes)[1]

    @property
    def target_humidity_step(self) -> float | None:
        return humidity_limits(self._target_attributes)[2]

    @property
    def supported_features(self) -> HumidifierEntityFeature:
        if effective_data(self._entry).get(CONF_MODE):
            return HumidifierEntityFeature.MODES
        return HumidifierEntityFeature(0)

    @property
    def available_modes(self) -> list[str] | None:
        if not self.supported_features:
            return None
        state = self._source_state(CONF_MODE)
        options = state.attributes.get("options") if state else None
        if not isinstance(options, (list, tuple)):
            return []
        return [option for option in options if isinstance(option, str)]

    @property
    def mode(self) -> str | None:
        state = self._source_state(CONF_MODE)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        return state.state

    @property
    def action(self) -> HumidifierAction | None:
        """Reserved for a future explicit compressor/activity source.

        Humidity above target does not prove the compressor is drying.
        Tank-full/defrost/power sensors are not activity sensors either.
        """
        return None

    @callback
    def _cancel_state_tracking(self) -> None:
        if self._unsubscribe_states is not None:
            self._unsubscribe_states()
            self._unsubscribe_states = None

    @callback
    def _track_sources(self) -> None:
        self._cancel_state_tracking()
        entity_ids = [self._sources[role] for role in STATE_ROLES if self._sources.get(role)]
        if entity_ids:
            self._unsubscribe_states = async_track_state_change_event(
                self.hass, entity_ids, self._state_changed
            )

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @callback
    def _registry_changed(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        """Resolve renames, remove/restore, disable/enable and unique_id changes."""
        data = effective_data(self._entry)
        refs = data.get(CONF_SOURCE_REFS, {})
        changed_ids = {event.data["entity_id"], event.data.get("old_entity_id")}
        bound_ids = {data.get(role) for role in self._sources} - {None}
        changed = er.async_get(self.hass).async_get(event.data["entity_id"])
        identity_match = changed is not None and any(
            ref["registry_id"] == changed.id
            or (ref["domain"], ref["platform"], ref["unique_id"])
            == (changed.domain, changed.platform, changed.unique_id)
            for ref in refs.values()
        )
        if not bound_ids.intersection(changed_ids) and not identity_match:
            return
        resolved = sync_entry_sources(self.hass, self._entry)
        if resolved != self._sources:
            _LOGGER.debug("Source bindings changed for device %s", self._device_id)
            self._sources = resolved
            self._track_sources()
        self.async_write_ha_state()

    @callback
    def _device_changed(self, event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Resolve again in case a source was renamed while this platform loaded.
        self._sources = sync_entry_sources(self.hass, self._entry)
        self._track_sources()
        self.async_on_remove(self._cancel_state_tracking)
        # A registry event listener also catches a removed source recreated with
        # a different entity_id, which a listener keyed only on old IDs cannot.
        self.async_on_remove(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed)
        )
        self.async_on_remove(
            async_track_device_registry_updated_event(
                self.hass, [self._device_id], self._device_changed
            )
        )

    async def _call_source(self, role: str, domain: str, service: str, data: dict[str, Any]) -> None:
        """Resolve at command time, propagate source failures and preserve context."""
        sources = resolve_sources(self.hass, effective_data(self._entry))
        entity_id = sources.get(role)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="source_unavailable")
        await self.hass.services.async_call(
            domain,
            service,
            {**data, ATTR_ENTITY_ID: entity_id},
            blocking=True,
            context=self._context,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._call_source(CONF_POWER, "switch", SERVICE_TURN_ON, {})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._call_source(CONF_POWER, "switch", SERVICE_TURN_OFF, {})

    async def async_set_humidity(self, humidity: int) -> None:
        if not valid_humidity_setting(
            humidity, self.min_humidity, self.max_humidity, self.target_humidity_step
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_humidity",
                translation_placeholders={
                    "min": str(self.min_humidity), "max": str(self.max_humidity),
                    "step": str(self.target_humidity_step or 1),
                },
            )
        await self._call_source(CONF_TARGET, "number", "set_value", {"value": humidity})

    async def async_set_mode(self, mode: str) -> None:
        if mode not in (self.available_modes or []):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_mode")
        await self._call_source(CONF_MODE, "select", "select_option", {"option": mode})
