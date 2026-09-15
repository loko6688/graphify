"""Local agent keystore. Public address only on the wire; secret stays on disk."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CARD_DIGITS = re.compile(r"^\d{13,19}$")
ETH_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Solana pubkeys: 32–44 chars, Bitcoin-style Base58 (no 0, O, I, l).
SOL_ADDR = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
# Tron USDT (TRC-20) receive addresses start with T.
TRON_ADDR = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
# 64-hex looks like a raw secp256k1 private key — never a payout destination.
RAW_PRIV = re.compile(r"^[0-9a-fA-F]{64}$")


class WalletError(ValueError):
    """Bad wallet path, destination, or secret handling."""


@dataclass(frozen=True)
class AgentWallet:
    path: Path
    address: str


def is_card_number(value: str) -> bool:
    compact = re.sub(r"[\s-]", "", value)
    return bool(CARD_DIGITS.match(compact))


def payout_chain(address: str) -> str:
    if ETH_ADDR.match(address):
        return "evm"
    if TRON_ADDR.match(address):
        return "tron"
    if SOL_ADDR.match(address) and not address.startswith("0x"):
        return "solana"
    raise WalletError("unknown payout chain")


def validate_payout_address(value: str) -> str:
    addr = value.strip()
    if not addr:
        raise WalletError("payout address is empty")
    if is_card_number(addr):
        raise WalletError("card numbers are not payout destinations")
    if RAW_PRIV.match(addr) or RAW_PRIV.match(addr.removeprefix("0x")):
        raise WalletError("private keys are not payout destinations")
    lowered = addr.lower()
    if any(k in lowered for k in ("seed", "mnemonic", "cvv", "cvc", "pan")):
        raise WalletError("secrets are not payout destinations")
    if ETH_ADDR.match(addr):
        return "0x" + addr[2:].lower()
    if TRON_ADDR.match(addr):
        return addr
    if SOL_ADDR.match(addr):
        return addr
    raise WalletError("payout address must be Solana, Tron T-addr, or 0x + 40 hex")


def derive_address(secret: bytes) -> str:
    digest = hashlib.sha256(b"money-agent-wallet-v1" + secret).hexdigest()
    return "0x" + digest[:40]


def create_wallet(path: Path) -> AgentWallet:
    path = path.expanduser()
    if path.exists():
        raise WalletError(f"wallet already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    address = derive_address(secret)
    payload = {
        "version": 1,
        "kind": "money-agent-local",
        "not_ethereum_secp256k1": True,
        "address": address,
        "secret_hex": secret.hex(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return AgentWallet(path=path, address=address)


def load_wallet(path: Path) -> AgentWallet:
    path = path.expanduser()
    data = json.loads(path.read_text())
    address = str(data["address"])
    secret = bytes.fromhex(str(data["secret_hex"]))
    if derive_address(secret) != address:
        raise WalletError("wallet file is corrupt")
    return AgentWallet(path=path, address=address)


def public_view(wallet: AgentWallet) -> dict[str, str]:
    return {"address": wallet.address, "path": str(wallet.path), "kind": "money-agent-local"}
