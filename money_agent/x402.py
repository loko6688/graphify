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
    pay_to: str | None = None

    def accepts(self) -> list[dict]:
        from money_agent.ways import SOLANA_USDC_MINT, SOLANA_USDT_MINT
        from money_agent.wallet import payout_chain

        if not self.pay_to:
            return [
                {
                    "scheme": "exact",
                    "network": "money-agent:ledger",
                    "maxAmountRequired": str(self.amount_micros),
                    "asset": "USD-ledger",
                    "payTo": "treasury",
                }
            ]
        chain = payout_chain(self.pay_to)
        if chain == "solana":
            return [
                {
                    "scheme": "exact",
                    "network": "solana:mainnet",
                    "maxAmountRequired": str(self.amount_micros),
                    "asset": SOLANA_USDC_MINT,
                    "payTo": self.pay_to,
                },
                {
                    "scheme": "exact",
                    "network": "solana:mainnet",
                    "maxAmountRequired": str(self.amount_micros),
                    "asset": SOLANA_USDT_MINT,
                    "payTo": self.pay_to,
                },
            ]
        if chain == "tron":
            return [
                {
                    "scheme": "exact",
                    "network": "tron:mainnet",
                    "maxAmountRequired": str(self.amount_micros),
                    "asset": "USDT",
                    "payTo": self.pay_to,
                }
            ]
        return [
            {
                "scheme": "exact",
                "network": "eip155:8453",
                "maxAmountRequired": str(self.amount_micros),
                "asset": "USDC",
                "payTo": self.pay_to,
            }
        ]

    def header(self) -> str:
        payload = {
            "scheme": "exact",
            "resource": self.resource,
            "amount": self.amount_micros,
            "invoice": self.invoice_id,
            "accepts": self.accepts(),
        }
        return "Payment " + json.dumps(payload, separators=(",", ":"))


def new_challenge(
    resource: str = INSIGHT_RESOURCE,
    amount: int = PRICE_MICROS,
    pay_to: str | None = None,
) -> Challenge:
    return Challenge(
        resource=resource, amount_micros=amount, invoice_id=secrets.token_hex(16), pay_to=pay_to
    )


def sign_proof(secret: bytes, challenge: Challenge, payer: str) -> str:
    msg = f"{challenge.invoice_id}|{challenge.amount_micros}|{payer}|{challenge.resource}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_proof(secret: bytes, challenge: Challenge, payer: str, proof: str) -> bool:
    expected = sign_proof(secret, challenge, payer)
    return hmac.compare_digest(expected, proof)
