# Money Agent

A bounded **merchant + buyer** agent. It sells a paid insight (`HTTP 402` / x402-style challenge), books every movement in integer micros, and can spend only from an operator-capped float.

**Paying itself does not print money.** Self-buys are internal transfers. Net assets rise only when an external buyer is funded (the simulated market, or a real wallet you wire later).

## Agent wallet + your payout address

The agent can create a **local keystore** (`~/.money-agent/agent.wallet.json`, mode `0600`). That file is gitignored. The HTTP API only ever shows the **public address**.

Payouts go to **your public Solana or `0x` wallet**. **Karten, CVV, Seed-Phrasen und Private Keys werden abgelehnt.**

```bash
python -m money_agent wallet --init
python -m money_agent payout-dest --to 4M7DGWMb4aGhdYktPwAkxQFZido81MeukReSgu2mJ2oM
python -m money_agent turbo --db ./money.sqlite --ticks 8 --customers 3
python -m money_agent serve --port 8765 --db ./money.sqlite
```

40% of excess stays as **credits** (working capital). The rest is booked to your Solana address. SPL **USDT** uses the same public key (`Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`). A separate Tron `T…` USDT address: `export MONEY_AGENT_USDT_ADDRESS=T...` (paste only the public address).

## Honest limits

- Ledger USD micros, not Solana mainnet settlement.
- The agent **cannot mint** a budget and **will not charge a card**.
- No scraping, spam, or “guaranteed yield.”

## HTTP

- `GET /` — live dashboard (Shift / Turbo / Sweep)
- `GET /api/wallet` — public addresses + chain (`solana` or `evm`)
- `POST /v1/turbo` — `{ "ticks": 5, "customers": 3 }`
- `POST /v1/payout` — `{ "amount_micros": 50000 }`
