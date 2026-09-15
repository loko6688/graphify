"""Legitimate rails only. No cards, no keys, no fake €500."""

from __future__ import annotations

# Circle USDC mint on Solana mainnet.
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

WAYS = [
    {
        "id": "x402-usdc",
        "what": "Charge other agents HTTP 402; they pay USDC; payTo is your public wallet",
        "needs": "A public payTo address (Solana or EVM). A facilitator to verify on-chain.",
        "real_today": False,
        "refs": [
            "https://docs.cdp.coinbase.com/coinbase-business/checkout-apis/accept-x402-payments",
            "https://docs.stripe.com/payments/machine/x402",
        ],
    },
    {
        "id": "solana-pay",
        "what": "Buyer signs a transfer to your Solana address (USDC mint below). You never hold their key.",
        "needs": "Your public address only. Buyer has USDC + Phantom.",
        "asset": SOLANA_USDC_MINT,
        "real_today": False,
        "refs": ["https://solana.com/docs/payments/how-payments-work"],
    },
    {
        "id": "not-this",
        "what": "Cards, seeds, private keys, spam, fake yield — refused",
        "needs": "Nothing. Do not send them.",
        "real_today": False,
        "refs": [],
    },
]


def ways_payload(pay_to: str | None = None) -> dict:
    return {
        "pay_to": pay_to,
        "min_500_eur_guaranteed": False,
        "real_settlement": False,
        "solana_usdc_mint": SOLANA_USDC_MINT,
        "ways": WAYS,
    }
