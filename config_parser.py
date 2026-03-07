"""Configuration parsing helpers for the Broadlink PG3 node server."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Dict


@dataclass
class PluginConfig:
    """Runtime configuration loaded from PG3 custom parameters."""

    user_id: str = ""
    user_password: str = ""
    hub_ip: str = ""
    ir_codes: Dict[str, str] = field(default_factory=dict)
    rf_codes: Dict[str, str] = field(default_factory=dict)


def _normalize_code_key(key: str) -> str:
    """Normalize user code names to stable labels."""
    return str(key).strip()


def parse_code_map(raw_value: str) -> Dict[str, str]:
    """Parse codes from JSON or line format.

    Supported formats:
    1) JSON object string:
       {"TV Power": "2600...", "AMP VolUp": "b64:AAEC..."}
    2) Multi-line key/value pairs:
       TV Power=2600...
       AMP VolUp=b64:AAEC...
    """
    if not raw_value:
        return {}

    text = str(raw_value).strip()
    if not text:
        return {}

    parsed: Dict[str, str] = {}

    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Code map JSON must be an object")
        for key, value in data.items():
            norm_key = _normalize_code_key(key)
            if not norm_key:
                continue
            parsed[norm_key] = str(value).strip()
        return parsed

    for line in text.splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#"):
            continue
        if "=" not in striped:
            raise ValueError(f"Invalid code line (missing '='): {striped}")
        key, value = striped.split("=", 1)
        norm_key = _normalize_code_key(key)
        if not norm_key:
            continue
        parsed[norm_key] = value.strip()

    return parsed


def build_config(custom_params: dict) -> PluginConfig:
    """Build PluginConfig from raw PG3 custom params."""
    params = custom_params or {}

    return PluginConfig(
        user_id=str(params.get("USER_ID", "")).strip(),
        user_password=str(params.get("USER_PASSWORD", "")).strip(),
        hub_ip=str(params.get("HUB_IP", "")).strip(),
        ir_codes=parse_code_map(str(params.get("IR_CODES", ""))),
        rf_codes=parse_code_map(str(params.get("RF_CODES", ""))),
    )
