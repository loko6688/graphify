"""Operator config: public payout address only. No cards, no seeds."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from money_agent.wallet import WalletError, payout_chain, validate_payout_address
from money_agent.x402 import PRICE_MICROS


@dataclass(frozen=True)
class OperatorConfig:
    payout_address: str | None
    usdt_address: str | None = None
    chain: str | None = None
    reserve_micros: int = PRICE_MICROS
    auto_payout: bool = True
    reinvest_bps: int = 4000


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
    usdt_raw = os.environ.get("MONEY_AGENT_USDT_ADDRESS") or data.get("usdt_address") or addr
    usdt = validate_payout_address(str(usdt_raw)) if usdt_raw else None
    chain = payout_chain(addr) if addr else None
    reserve = int(os.environ.get("MONEY_AGENT_RESERVE_MICROS") or data.get("reserve_micros") or PRICE_MICROS)
    auto = os.environ.get("MONEY_AGENT_AUTO_PAYOUT", str(data.get("auto_payout", True))).lower() in {
        "1",
        "true",
        "yes",
    }
    reinvest = int(os.environ.get("MONEY_AGENT_REINVEST_BPS") or data.get("reinvest_bps") or 4000)
    reinvest = max(0, min(reinvest, 9000))
    return OperatorConfig(
        payout_address=addr,
        usdt_address=usdt,
        chain=chain,
        reserve_micros=max(0, reserve),
        auto_payout=auto,
        reinvest_bps=reinvest,
    )


def save_config(update: dict, path: Path | None = None) -> OperatorConfig:
    cfg = config_path(path)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_file(cfg)
    if "payout_address" in update and update["payout_address"]:
        payload["payout_address"] = validate_payout_address(str(update["payout_address"]))
        payload["chain"] = payout_chain(payload["payout_address"])
    if "usdt_address" in update and update["usdt_address"]:
        payload["usdt_address"] = validate_payout_address(str(update["usdt_address"]))
    if "reserve_micros" in update:
        payload["reserve_micros"] = int(update["reserve_micros"])
    if "auto_payout" in update:
        payload["auto_payout"] = bool(update["auto_payout"])
    if "reinvest_bps" in update:
        payload["reinvest_bps"] = max(0, min(int(update["reinvest_bps"]), 9000))
    cfg.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(cfg, 0o600)
    return load_config(cfg)


def save_payout_address(address: str, path: Path | None = None) -> OperatorConfig:
    return save_config({"payout_address": address, "usdt_address": address}, path)


def require_payout_address(cfg: OperatorConfig) -> str:
    if not cfg.payout_address:
        raise WalletError(
            "set MONEY_AGENT_PAYOUT_ADDRESS or: python -m money_agent payout-dest --to <solana-or-0x>"
        )
    return cfg.payout_address
