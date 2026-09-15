# Money Agent

A bounded **merchant + buyer** agent. It sells a paid insight (`HTTP 402` / x402-style challenge), books every movement in integer micros, and can spend only from an operator-capped float.

**Paying itself does not print money.** Self-buys are internal transfers. Net assets rise only when an external buyer is funded (the simulated market, or a real wallet you wire later).

## Agent wallet + your payout address

The agent can create a **local keystore** (`~/.money-agent/agent.wallet.json`, mode `0600`). That file is gitignored. The HTTP API only ever shows the **public address**.

Payouts go to **your public `0x` wallet**, set via env or CLI. **Karten, CVV, Seed-Phrasen und Private Keys werden abgelehnt** — nicht in den Chat, nicht in JSON.

```bash
python -m money_agent wallet --init
export MONEY_AGENT_PAYOUT_ADDRESS=0xYourPublicAddressHere000000000000000000
# or:
python -m money_agent payout-dest --to 0xYourPublicAddressHere000000000000000000

python -m money_agent shift --customers 5 --db ./money.sqlite
python -m money_agent turbo --db ./money.sqlite --ticks 8 --customers 3
python -m money_agent serve --port 8765 --db ./money.sqlite
```

`turbo` fährt mehrere Shifts und sweeped Treasury über der Reserve (`PRICE`, default $0.05) auf deine 0x-Adresse.

## Serve

```bash
python -m money_agent serve --port 8765 --db ./money.sqlite
```

`payout` bucht Treasury → deine Adresse im Ledger. On-chain Broadcast brauchst du mit deinem eigenen Signer (MetaMask, Coinbase, AgentCore). Diese Datei ist **kein** Ethereum-secp256k1-Key für Mainnet.

## Honest limits

- This ledger is **local USD micros**, not Coinbase/Stripe card settlement.
- The agent **cannot mint** a budget and **will not charge a card**.
- No scraping, spam, or “guaranteed yield.”

## Serve

```bash
python -m money_agent serve --port 8765 --db ./money.sqlite
```

- `GET /` — treasury, payout dest, agent address
- `GET /api/wallet` — public addresses only
- `POST /v1/payout` — `{"amount_micros":50000}` (optional `"to"` must match config)
