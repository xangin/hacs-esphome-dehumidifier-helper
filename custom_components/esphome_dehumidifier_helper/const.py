"""Integration identity, source roles, and conservative discovery rules."""

from typing import Final

DOMAIN: Final = "esphome_dehumidifier_helper"
NAME: Final = "ESPHome Dehumidifier Helper"
MANUFACTURER: Final = "Simon IoT"
MODEL: Final = "ESPHome Dehumidifier Helper"
# Optional firmware recognition hints; other ESPHome brands use structural discovery.
# Firmware project identifiers are independent of this integration's domain.
KNOWN_ESPHOME_PROJECTS: Final = ("simon_iot.hitachi_dehumidifier",)
ESPHOME_DOMAIN: Final = "esphome"

CONF_DEVICE_ID: Final = "device_id"
CONF_POWER: Final = "power_entity_id"
CONF_HUMIDITY: Final = "humidity_entity_id"
CONF_TARGET: Final = "target_humidity_entity_id"
CONF_MODE: Final = "mode_entity_id"
CONF_MODE_NAMES: Final = "mode_names"
CONF_FAN: Final = "fan_entity_id"
CONF_SOURCE_REFS: Final = "source_refs"

REQUIRED_ROLES: Final = (CONF_POWER, CONF_HUMIDITY, CONF_TARGET)
OPTIONAL_ROLES: Final = (CONF_MODE, CONF_FAN)
ROLES: Final = REQUIRED_ROLES + OPTIONAL_ROLES
STATE_ROLES: Final = REQUIRED_ROLES + (CONF_MODE,)
ROLE_DOMAINS: Final = {
    CONF_POWER: ("switch",),
    CONF_HUMIDITY: ("sensor",),
    CONF_TARGET: ("number",),
    CONF_MODE: ("select",),
    # Older ST01 firmware exposes a native fan instead of a select.
    CONF_FAN: ("select", "fan"),
}

# Original names supplied by ESPHome, never substrings of an entity_id.
ROLE_NAMES: Final = {
    CONF_POWER: ("電源", "power", "power switch"),
    CONF_HUMIDITY: ("濕度", "目前濕度", "humidity", "humidity indoor"),
    CONF_TARGET: ("設定濕度", "目標濕度", "target humidity", "relative humidity"),
    CONF_MODE: ("運轉模式", "operation mode", "operating mode"),
    CONF_FAN: ("風量", "風速", "fan speed", "fan level", "fan"),
}

FALLBACK_MIN_HUMIDITY: Final = 40.0
FALLBACK_MAX_HUMIDITY: Final = 80.0

# Applied to known Hitachi firmware, or a select offering all four ST01 modes.
HITACHI_MODE_NAMES: Final = {
    "eco": "舒適節電",
    "normal": "自訂濕度",
    "boost": "快速乾衣",
    "home": "低濕乾燥",
}
