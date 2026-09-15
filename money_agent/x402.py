"""Minimal x402-style challenge + HMAC proof. Not a chain settlement."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass

INSIGHT_RESOURCE = "/v1/insight"
PRICE_MICROS = 50_000  # $0.05


@dataclass(frozen=True)
class Challenge:
    resource: str
    amount_micros: int
    invoice_id: str

    def header(self) -> str:
        payload = {
            "scheme": "exact",
            "resource": self.resource,
            "amount": self.amount_micros,
            "invoice": self.invoice_id,
            "asset": "USD-ledger",
        }
        return "Payment " + json.dumps(payload, separators=(",", ":"))


def new_challenge(resource: str = INSIGHT_RESOURCE, amount: int = PRICE_MICROS) -> Challenge:
    return Challenge(resource=resource, amount_micros=amount, invoice_id=secrets.token_hex(16))


def sign_proof(secret: bytes, challenge: Challenge, payer: str) -> str:
    msg = f"{challenge.invoice_id}|{challenge.amount_micros}|{payer}|{challenge.resource}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_proof(secret: bytes, challenge: Challenge, payer: str, proof: str) -> bool:
    expected = sign_proof(secret, challenge, payer)
    return hmac.compare_digest(expected, proof)
