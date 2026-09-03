"""Offline behavior checks; registry doubles do not replace real HA testing.

Run: python3 -m unittest discover -s tests -v
No Home Assistant installation, network, or ESPHome environment is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "esphome_dehumidifier_helper"


@dataclass
class Source:
    entity_id: str
    domain: str
    original_name: str
    device_id: str = "device-one"
    platform: str = "esphome"
    original_device_class: str | None = None
    device_class: str | None = None
    unit_of_measurement: str | None = None
    disabled_by: str | None = None
    entity_category: str | None = None
    id: str = ""
    unique_id: str = ""

    def __post_init__(self) -> None:
        self.id = self.id or "uuid:" + self.entity_id
        self.unique_id = self.unique_id or "unique:" + self.entity_id


class Registry:
    def __init__(self, entries: list[Source]) -> None:
        self.entries = entries

    def async_get(self, identity: str) -> Source | None:
        return next((entry for entry in self.entries if identity in (entry.id, entry.entity_id)), None)

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str) -> str | None:
        return next(
            (entry.entity_id for entry in self.entries
             if (entry.domain, entry.platform, entry.unique_id) == (domain, platform, unique_id)),
            None,
        )


@dataclass
class Device:
    id: str
    name: str = "Same display name"
    name_by_user: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    disabled_by: str | None = None
    identifiers: set[tuple[str, str]] = field(default_factory=set)
    connections: set[tuple[str, str]] = field(default_factory=set)
    config_entries: set[str] = field(default_factory=lambda: {"esphome-entry"})


def load_helpers():
    """Use tiny public-registry test doubles only during helper imports."""
    modules = {name: ModuleType(name) for name in (
        "homeassistant", "homeassistant.core", "homeassistant.config_entries",
        "homeassistant.helpers", "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.device_registry", "dehumidifier_helper_offline",
    )}
    modules["dehumidifier_helper_offline"].__path__ = [str(COMPONENT)]
    core = modules["homeassistant.core"]
    core.HomeAssistant = object
    core.callback = lambda function: function
    modules["homeassistant.config_entries"].ConfigEntry = object
    entity_registry = modules["homeassistant.helpers.entity_registry"]
    entity_registry.RegistryEntry = Source
    entity_registry.async_get = lambda hass: hass.registry
    entity_registry.async_entries_for_device = lambda registry, device_id: [
        entry for entry in registry.entries if entry.device_id == device_id
    ]
    device_registry = modules["homeassistant.helpers.device_registry"]
    device_registry.DeviceEntry = Device
    device_registry.CONNECTION_NETWORK_MAC = "mac"
    device_registry.async_get = lambda hass: hass.devices
    with patch.dict(sys.modules, modules):
        return tuple(importlib.import_module("dehumidifier_helper_offline." + module) for module in (
            "const", "values", "discovery", "bindings"
        ))


C, values, discovery, bindings = load_helpers()


class LogicTests(unittest.TestCase):
    def setUp(self) -> None:
        # Opaque entity IDs are intentionally unrelated to their functions.
        self.sources = [
            Source("switch.x7", "switch", "電源"),
            Source("sensor.x3", "sensor", "濕度", original_device_class="humidity", unit_of_measurement="%"),
            Source("number.x9", "number", "設定濕度"),
            Source("select.x4", "select", "運轉模式"),
            Source("select.x8", "select", "風量"),
        ]
        self.registry = Registry(self.sources)
        self.states: dict[str, SimpleNamespace] = {}
        self.device = Device("device-one", connections={("mac", "01:02:03:04:05:06")})
        self.hass = SimpleNamespace(
            registry=self.registry,
            states=SimpleNamespace(get=self.states.get),
            devices=SimpleNamespace(devices={self.device.id: self.device}),
            config_entries=SimpleNamespace(
                async_get_entry=lambda entry_id: SimpleNamespace(domain="esphome"),
                async_update_entry=lambda entry, **updates: entry.__dict__.update(updates),
            ),
        )

    def test_chinese_sources_with_opaque_ids(self) -> None:
        detected = discovery.detect_entities(self.hass, self.device.id)
        self.assertEqual(detected.manual_roles, ())
        self.assertEqual(detected.entities[C.CONF_POWER], "switch.x7")
        self.assertEqual(detected.entities[C.CONF_HUMIDITY], "sensor.x3")
        self.assertEqual(detected.entities[C.CONF_TARGET], "number.x9")
        self.assertEqual(detected.entities[C.CONF_MODE], "select.x4")
        self.assertEqual(detected.entities[C.CONF_FAN], "select.x8")

    def test_legacy_st01_english_names_and_native_fan(self) -> None:
        for source, name in zip(self.sources, (
            "Power Switch", "Humidity Indoor", "Relative Humidity", "Operation Mode", "Fan"
        ), strict=True):
            source.original_name = name
        self.sources[-1].domain = "fan"
        self.sources[-1].entity_id = "fan.x8"
        self.sources.append(Source("switch.extra", "switch", "Lock"))
        self.assertEqual(discovery.detect_entities(self.hass, self.device.id).manual_roles, ())

    def test_domain_is_not_inferred_from_name(self) -> None:
        self.sources[2].original_name = "電源"
        result = discovery.detect_entities(self.hass, self.device.id)
        self.assertIsNone(result.entities[C.CONF_TARGET])
        self.assertEqual(result.entities[C.CONF_POWER], "switch.x7")

    def test_device_class_precedes_original_name(self) -> None:
        self.sources[1].original_name = "Unrelated label"
        self.sources.append(Source("sensor.decoy", "sensor", "濕度"))
        result = discovery.detect_entities(self.hass, self.device.id)
        self.assertEqual(result.entities[C.CONF_HUMIDITY], "sensor.x3")

    def test_state_device_class_fallback(self) -> None:
        self.sources[1].original_device_class = None
        self.sources[1].original_name = "測量值"
        self.states["sensor.x3"] = SimpleNamespace(attributes={"device_class": "humidity"})
        self.assertEqual(discovery.detect_entities(self.hass, self.device.id).entities[C.CONF_HUMIDITY], "sensor.x3")

    def test_ambiguous_power_requires_manual_choice(self) -> None:
        self.sources.append(Source("switch.duplicate", "switch", "電源"))
        result = discovery.detect_entities(self.hass, self.device.id)
        self.assertIsNone(result.entities[C.CONF_POWER])
        self.assertIn(C.CONF_POWER, result.manual_roles)

    def test_single_switch_fallback(self) -> None:
        self.sources[0].original_name = "啟動"
        self.assertEqual(discovery.detect_entities(self.hass, self.device.id).entities[C.CONF_POWER], "switch.x7")

    def test_target_percent_fallback(self) -> None:
        self.sources[2].original_name = "目標值"
        self.sources[2].unit_of_measurement = "%"
        self.assertEqual(discovery.detect_entities(self.hass, self.device.id).entities[C.CONF_TARGET], "number.x9")

    def test_absent_optional_sources_do_not_force_manual_selection(self) -> None:
        self.sources[:] = self.sources[:3]
        result = discovery.detect_entities(self.hass, self.device.id)
        self.assertEqual(result.manual_roles, ())
        self.assertIsNone(result.entities[C.CONF_MODE])

    def test_disabled_and_non_esphome_entities_are_excluded(self) -> None:
        self.sources[0].disabled_by = "user"
        self.sources.append(Source("switch.foreign", "switch", "電源", platform="other"))
        self.assertIsNone(discovery.detect_entities(self.hass, self.device.id).entities[C.CONF_POWER])

    def test_multiple_devices_remain_isolated(self) -> None:
        second = [replace(source, device_id="device-two", entity_id=source.entity_id + "_2", id="", unique_id="") for source in self.sources]
        self.sources.extend(second)
        first = discovery.detect_entities(self.hass, "device-one")
        other = discovery.detect_entities(self.hass, "device-two")
        self.assertEqual(first.entities[C.CONF_POWER], "switch.x7")
        self.assertEqual(other.entities[C.CONF_POWER], "switch.x7_2")
        invalid = first.entities | {C.CONF_POWER: "switch.x7_2"}
        self.assertEqual(bindings.validate_sources(self.hass, "device-one", invalid)[C.CONF_POWER], "invalid_entity")

    def test_unique_id_ignores_name_and_suffix(self) -> None:
        before = discovery.device_unique_id(self.device)
        self.device.name = "任意新名稱 不是 MAC"
        self.assertEqual(before, discovery.device_unique_id(self.device))
        other = replace(self.device, id="second", connections={("mac", "11:12:13:14:15:16")})
        self.assertNotEqual(before, discovery.device_unique_id(other))

    def test_candidates_filter_structure_and_prefer_project_hint(self) -> None:
        plain = Device("plain")
        project = Device("project", manufacturer="simon_iot", model="hitachi_dehumidifier")
        self.hass.devices.devices.update({plain.id: plain, project.id: project})
        self.assertEqual([d.id for d in discovery.eligible_devices(self.hass)], ["project", "device-one"])

    def test_rename_then_reload_resolves_uuid_and_syncs_config(self) -> None:
        selected = discovery.detect_entities(self.hass, self.device.id).entities
        data = bindings.serialize_sources(self.hass, self.device.id, selected)
        self.sources[0].entity_id = "switch.renamed_completely"
        entry = SimpleNamespace(data=data, options=dict(data))
        resolved = bindings.sync_entry_sources(self.hass, entry)
        self.assertEqual(resolved[C.CONF_POWER], "switch.renamed_completely")
        self.assertEqual(entry.data[C.CONF_POWER], "switch.renamed_completely")
        self.assertEqual(entry.options[C.CONF_POWER], "switch.renamed_completely")
        self.assertEqual(bindings.resolve_sources(self.hass, bindings.effective_data(entry)), resolved)

    def test_reused_old_entity_id_is_never_trusted(self) -> None:
        data = bindings.serialize_sources(self.hass, self.device.id, discovery.detect_entities(self.hass, self.device.id).entities)
        self.sources.pop(0)
        self.sources.insert(0, Source("switch.x7", "switch", "電源", id="different-uuid", unique_id="different-source"))
        self.assertIsNone(bindings.resolve_sources(self.hass, data)[C.CONF_POWER])

    def test_unique_id_recovers_recreated_registry_entry(self) -> None:
        data = bindings.serialize_sources(self.hass, self.device.id, discovery.detect_entities(self.hass, self.device.id).entities)
        self.sources[0].id = "new-registry-uuid"
        self.sources[0].entity_id = "switch.restored"
        self.assertEqual(bindings.resolve_sources(self.hass, data)[C.CONF_POWER], "switch.restored")

    def test_optional_can_be_cleared(self) -> None:
        data = bindings.serialize_sources(self.hass, self.device.id, discovery.detect_entities(self.hass, self.device.id).entities)
        selected = discovery.detect_entities(self.hass, self.device.id).entities | {C.CONF_MODE: None}
        options = bindings.serialize_sources(self.hass, self.device.id, selected)
        entry = SimpleNamespace(data=data, options=options)
        self.assertIsNone(bindings.sync_entry_sources(self.hass, entry)[C.CONF_MODE])
        self.assertIsNone(entry.data[C.CONF_MODE])
        self.assertNotIn(C.CONF_MODE, entry.data[C.CONF_SOURCE_REFS])

    def test_duplicate_mode_and_fan_are_rejected(self) -> None:
        selected = discovery.detect_entities(self.hass, self.device.id).entities
        selected[C.CONF_FAN] = selected[C.CONF_MODE]
        self.assertEqual(bindings.validate_sources(self.hass, self.device.id, selected)[C.CONF_FAN], "duplicate_entity")

    def test_missing_source_recovers_after_enable(self) -> None:
        data = bindings.serialize_sources(self.hass, self.device.id, discovery.detect_entities(self.hass, self.device.id).entities)
        self.sources[0].disabled_by = "user"
        entry = SimpleNamespace(data=data, options={})
        self.assertIsNone(bindings.sync_entry_sources(self.hass, entry)[C.CONF_POWER])
        self.assertIn(C.CONF_POWER, entry.data[C.CONF_SOURCE_REFS])
        self.sources[0].disabled_by = None
        self.assertEqual(bindings.sync_entry_sources(self.hass, entry)[C.CONF_POWER], "switch.x7")

    def test_bad_humidity_states_are_safe(self) -> None:
        for value in (None, "unknown", "unavailable", "nonnumeric", "NaN", "inf", True, -1, 101):
            with self.subTest(value=value):
                self.assertIsNone(values.humidity_value(value))
        self.assertEqual(values.humidity_value("55.5"), 55.5)

    def test_limits_and_step_come_from_number(self) -> None:
        self.assertEqual(values.humidity_limits({"min": 30, "max": 90, "step": 5}), (30, 90, 5))
        self.assertEqual(values.humidity_limits({}), (40, 80, None))
        self.assertEqual(values.humidity_limits({"min": "NaN", "max": 80, "step": 0}), (40, 80, None))
        self.assertTrue(values.valid_humidity_setting(55, 30, 90, 5))
        self.assertFalse(values.valid_humidity_setting(56, 30, 90, 5))
        self.assertFalse(values.valid_humidity_setting(91, 30, 90, 5))


if __name__ == "__main__":
    unittest.main()
