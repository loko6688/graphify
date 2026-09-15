"""Legitimate rails only. No cards, no keys, no fake €500."""

from __future__ import annotations

# Circle USDC and Tether USDT on Solana mainnet.
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

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
        "id": "solana-usdt",
        "what": "Same Solana wallet can receive USDT (SPL). Optional extra Tron T-address via MONEY_AGENT_USDT_ADDRESS.",
        "needs": "Public address only. Buyer signs. No private key.",
        "asset": SOLANA_USDT_MINT,
        "real_today": False,
        "refs": ["https://solana.com/docs/payments/how-payments-work"],
    },
    {
        "id": "reinvest-credits",
        "what": "Keep a cut of earnings as credits (working capital) instead of paying all out. Not an APY.",
        "needs": "MONEY_AGENT_REINVEST_BPS (default 4000 = 40%).",
        "real_today": False,
        "refs": [],
    },
    {
        "id": "not-this",
        "what": "Cards, seeds, private keys, spam, fake yield — refused",
        "needs": "Nothing. Do not send them.",
        "real_today": False,
        "refs": [],
    },
]


def ways_payload(pay_to: str | None = None, usdt_to: str | None = None) -> dict:
    return {
        "pay_to": pay_to,
        "usdt_to": usdt_to or pay_to,
        "min_500_eur_guaranteed": False,
        "real_settlement": False,
        "solana_usdc_mint": SOLANA_USDC_MINT,
        "solana_usdt_mint": SOLANA_USDT_MINT,
        "ways": WAYS,
    }
