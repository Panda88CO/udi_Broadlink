"""Configuration parsing helpers for the Broadlink PG3 node server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PluginConfig:
    """Runtime configuration loaded from PG3 custom parameters."""

    user_id: str = ""
    user_password: str = ""
    hub_ip: str = ""
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_security_mode: int = 4
    setup_ip: str = "255.255.255.255"
    ir_codes: Dict[str, str] = field(default_factory=dict)
    rf_codes: Dict[str, str] = field(default_factory=dict)


def _normalize_code_key(key: str) -> str:
    """Normalize user code names to stable labels."""
    return str(key).strip()


def parse_prefixed_codes(custom_params: dict, prefix: str) -> Dict[str, str]:
    """Parse code mappings from individual PG3 custom parameters.

    Example:
    - IR_TV_POWER=2600d200...
    - RF_FAN_ON=b64:AAECAw...

    The portion after the prefix (for example, ``TV_POWER``) becomes the
    dynamic node code name.
    """
    params = custom_params or {}
    wanted_prefix = f"{prefix.upper()}_"
    parsed: Dict[str, str] = {}

    for raw_key, raw_value in params.items():
        key = str(raw_key).strip()
        if not key:
            continue

        if not key.upper().startswith(wanted_prefix):
            continue

        code_name = _normalize_code_key(key[len(wanted_prefix) :])
        code_value = str(raw_value).strip()
        if not code_name or not code_value:
            continue

        parsed[code_name] = code_value

    return parsed


def build_config(custom_params: dict) -> PluginConfig:
    """Build PluginConfig from raw PG3 custom params."""
    params = custom_params or {}

    wifi_security_mode = 4
    try:
        wifi_security_mode = int(params.get("WIFI_SECURITY_MODE", 4))
    except (TypeError, ValueError):
        wifi_security_mode = 4

    return PluginConfig(
        user_id=str(params.get("USER_ID", "")).strip(),
        user_password=str(params.get("USER_PASSWORD", "")).strip(),
        hub_ip=str(params.get("HUB_IP", "")).strip(),
        wifi_ssid=str(params.get("WIFI_SSID", "")).strip(),
        wifi_password=str(params.get("WIFI_PASSWORD", "")).strip(),
        wifi_security_mode=wifi_security_mode,
        setup_ip=str(params.get("SETUP_IP", "255.255.255.255")).strip() or "255.255.255.255",
        ir_codes=parse_prefixed_codes(params, "IR"),
        rf_codes=parse_prefixed_codes(params, "RF"),
    )
