"""Operator config: public payout address only. No cards, no seeds."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from money_agent.wallet import WalletError, validate_payout_address


@dataclass(frozen=True)
class OperatorConfig:
    payout_address: str | None


def config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("MONEY_AGENT_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".money-agent" / "config.json"


def load_config(path: Path | None = None) -> OperatorConfig:
    env_addr = os.environ.get("MONEY_AGENT_PAYOUT_ADDRESS")
    file_addr = None
    cfg = config_path(path)
    if cfg.is_file():
        data = json.loads(cfg.read_text())
        file_addr = data.get("payout_address")
    raw = env_addr or file_addr
    if not raw:
        return OperatorConfig(payout_address=None)
    return OperatorConfig(payout_address=validate_payout_address(str(raw)))


def save_payout_address(address: str, path: Path | None = None) -> OperatorConfig:
    validated = validate_payout_address(address)
    cfg = config_path(path)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    payload = {"payout_address": validated}
    cfg.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(cfg, 0o600)
    return OperatorConfig(payout_address=validated)


def require_payout_address(cfg: OperatorConfig) -> str:
    if not cfg.payout_address:
        raise WalletError(
            "set MONEY_AGENT_PAYOUT_ADDRESS or: python -m money_agent payout-dest --to 0x..."
        )
    return cfg.payout_address
