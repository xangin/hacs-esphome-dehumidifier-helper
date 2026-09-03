"""Editable mode names with reversible mappings to the source select options."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr, selector

from .bindings import resolve_sources
from .const import CONF_DEVICE_ID, CONF_MODE, CONF_MODE_NAMES, HITACHI_MODE_NAMES
from .discovery import project_hint


def mode_options(state: State | None) -> list[str]:
    """Keep the actual source values and order, including non-English options."""
    options = state.attributes.get("options") if state else None
    if not isinstance(options, (list, tuple)):
        return []
    return list(dict.fromkeys(option for option in options if isinstance(option, str) and option))


def suggested_mode_names(
    options: Sequence[str], saved: Mapping[str, str], *, hitachi: bool = False
) -> dict[str, str]:
    """Prefer saved names; generic devices otherwise keep their own options."""
    defaults = HITACHI_MODE_NAMES if hitachi or HITACHI_MODE_NAMES.keys() <= set(options) else {}
    return {
        option: saved.get(option, defaults.get(option, option)).strip() or option
        for option in options
    }


@callback
def source_mode_names(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    """Read the selected source through stable registry references."""
    entity_id = resolve_sources(hass, data).get(CONF_MODE)
    state = hass.states.get(entity_id) if entity_id else None
    device = dr.async_get(hass).async_get(data[CONF_DEVICE_ID])
    return suggested_mode_names(
        mode_options(state), data.get(CONF_MODE_NAMES, {}),
        hitachi=device is not None and project_hint(device),
    )


def unique_mode_names(names: Mapping[str, str]) -> dict[str, str]:
    """If firmware changes cause collisions, use source names until corrected.

    Never let two source options share a displayed name: reversing it could
    send the wrong command. Configuration rejects collisions before saving.
    """
    if len(set(names.values())) != len(names):
        return {option: option for option in names}
    return dict(names)


@callback
def mode_names_schema(names: Mapping[str, str]) -> vol.Schema:
    """Render one ordinary text field per option using HA's structured editor."""
    if not names:
        return vol.Schema({})
    return vol.Schema({
        vol.Required(CONF_MODE_NAMES, default=dict(names)): selector.ObjectSelector(
            selector.ObjectSelectorConfig(fields={
                option: selector.ObjectSelectorField(
                    label=option, selector=selector.TextSelector(), required=False
                )
                for option in names
            })
        )
    })


def submitted_mode_names(
    suggestions: Mapping[str, str], user_input: Mapping[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate uniqueness, and let blank fields restore the original option."""
    supplied = user_input.get(CONF_MODE_NAMES, suggestions)
    if not isinstance(supplied, dict) or any(not isinstance(value, str) for value in supplied.values()):
        return {}, {CONF_MODE_NAMES: "invalid_mode_names"}
    if supplied.keys() - suggestions.keys():
        return {}, {CONF_MODE_NAMES: "mode_options_changed"}
    names = {option: supplied.get(option, "").strip() or option for option in suggestions}
    if len(set(names.values())) != len(names):
        return names, {CONF_MODE_NAMES: "duplicate_mode_names"}
    return names, {}
