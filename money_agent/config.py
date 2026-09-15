"""Operator config: public payout address only. No cards, no seeds."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from money_agent.wallet import WalletError, validate_payout_address
from money_agent.x402 import PRICE_MICROS


@dataclass(frozen=True)
class OperatorConfig:
    payout_address: str | None
    reserve_micros: int = PRICE_MICROS
    auto_payout: bool = True


def config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("MONEY_AGENT_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".money-agent" / "config.json"


def _read_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def load_config(path: Path | None = None) -> OperatorConfig:
    cfg = config_path(path)
    data = _read_file(cfg)
    env_addr = os.environ.get("MONEY_AGENT_PAYOUT_ADDRESS")
    raw = env_addr or data.get("payout_address")
    addr = validate_payout_address(str(raw)) if raw else None
    reserve = int(os.environ.get("MONEY_AGENT_RESERVE_MICROS") or data.get("reserve_micros") or PRICE_MICROS)
    auto = os.environ.get("MONEY_AGENT_AUTO_PAYOUT", str(data.get("auto_payout", True))).lower() in {
        "1",
        "true",
        "yes",
    }
    return OperatorConfig(payout_address=addr, reserve_micros=max(0, reserve), auto_payout=auto)


def save_config(update: dict, path: Path | None = None) -> OperatorConfig:
    cfg = config_path(path)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_file(cfg)
    if "payout_address" in update and update["payout_address"]:
        payload["payout_address"] = validate_payout_address(str(update["payout_address"]))
    if "reserve_micros" in update:
        payload["reserve_micros"] = int(update["reserve_micros"])
    if "auto_payout" in update:
        payload["auto_payout"] = bool(update["auto_payout"])
    cfg.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(cfg, 0o600)
    return load_config(cfg)


def save_payout_address(address: str, path: Path | None = None) -> OperatorConfig:
    return save_config({"payout_address": address}, path)


def require_payout_address(cfg: OperatorConfig) -> str:
    if not cfg.payout_address:
        raise WalletError(
            "set MONEY_AGENT_PAYOUT_ADDRESS or: python -m money_agent payout-dest --to 0x..."
        )
    return cfg.payout_address
