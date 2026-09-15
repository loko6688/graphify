# Money Agent

A bounded **merchant + buyer** agent. It sells a paid insight (`HTTP 402` / x402-style challenge), books every movement in integer micros, and can spend only from an operator-capped float.

**Paying itself does not print money.** Self-buys are internal transfers. Net assets rise only when an external buyer is funded (the simulated market, or a real wallet you wire later).

## Honest limits

- This ledger is **local USD micros**, not Coinbase/Stripe settlement.
- Live USDC needs AgentCore Payments (or another wallet) plus a human-approved spend session. The agent **cannot mint** a budget.
- No scraping, spam, or “guaranteed yield.” Revenue is a paid lookup you actually deliver.

## Run a shift

```bash
python -m money_agent shift --customers 5
```

## Serve dashboard + 402 API

```bash
python -m money_agent serve --port 8765
```

- `GET /` — treasury, agent float, net assets
- `GET /api/books` — JSON ledger
- `GET /v1/insight?q=...` — `402 Payment Required` until a valid HMAC proof
- `POST /v1/shift` — `{"customers":3}` runs a simulated earning shift
