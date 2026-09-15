"""Local HTTP surface: live dashboard, 402 insight, turbo earn, owner payout."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from money_agent.agent import MoneyAgent
from money_agent.config import OperatorConfig
from money_agent.engine import run_turbo, sweep_excess, turbo_public
from money_agent.wallet import AgentWallet, WalletError, validate_payout_address
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS, new_challenge, sign_proof, verify_proof

FORBIDDEN_PAYOUT_KEYS = frozenset(
    {
        "card",
        "card_number",
        "number",
        "pan",
        "cvv",
        "cvc",
        "expiry",
        "exp",
        "seed",
        "mnemonic",
        "private_key",
        "secret",
        "secret_hex",
    }
)

DASHBOARD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Money Agent</title>
<style>
body{font-family:ui-sans-serif,system-ui;background:#0b1220;color:#e8eefc;margin:0;padding:2rem}
.card{max-width:52rem;margin:auto;background:#152038;border-radius:16px;padding:1.5rem 2rem}
h1{margin-top:0} .num{font-variant-numeric:tabular-nums}
.row{display:flex;gap:.6rem;flex-wrap:wrap;margin:1rem 0}
button{background:#22c55e;color:#052e16;border:0;border-radius:8px;padding:.55rem 1rem;font-weight:700;cursor:pointer}
.warn{color:#fbbf24;font-size:.9rem} code{word-break:break-all}
table{width:100%;font-size:.85rem;border-collapse:collapse} td,th{text-align:left;padding:.3rem 0;border-bottom:1px solid #243656}
</style></head><body><div class="card">
<h1>Money Agent</h1>
<p>Earn, then sweep treasury to <b>your public 0x address</b>. No cards. No seeds.</p>
<p class="num" id="books">Loading…</p>
<p>Agent: <code id="wallet">$WALLET</code><br>Payout: <code id="dest">$DEST</code></p>
<div class="row">
<button id="shift">Run shift (3 buyers)</button>
<button id="turbo">Turbo (5 ticks + auto payout)</button>
<button id="sweep">Sweep excess</button>
</div>
<p class="warn">Ledger USD. Broadcast on-chain with your own signer.</p>
<h2>Activity</h2>
<table><thead><tr><th>kind</th><th>amount</th><th>memo</th></tr></thead><tbody id="act"></tbody></table>
<script>
async function refresh(){
  const b = await (await fetch('/api/books')).json();
  const usd = n => '$'+(n/1e6).toFixed(2);
  document.getElementById('books').innerHTML =
    'Treasury '+usd(b.treasury_micros)+' · Agent '+usd(b.agent_micros)+
    ' · Paid out '+usd(b.payout_micros)+' · Net '+usd(b.net_assets_micros);
  const a = await (await fetch('/api/activity')).json();
  document.getElementById('act').innerHTML = a.entries.map(e =>
    '<tr><td>'+e.kind+'</td><td>'+usd(e.amount_micros)+'</td><td>'+e.memo+'</td></tr>'
  ).join('');
}
async function post(url, body){
  await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  await refresh();
}
document.getElementById('shift').onclick = () => post('/v1/shift',{customers:3});
document.getElementById('turbo').onclick = () => post('/v1/turbo',{ticks:5,customers:3});
document.getElementById('sweep').onclick = () => post('/v1/sweep',{});
refresh();
</script>
</div></body></html>
"""


def usd(micros: int) -> str:
    sign = "-" if micros < 0 else ""
    value = abs(micros)
    return f"{sign}${value / 1_000_000:.2f}"


class Handler(BaseHTTPRequestHandler):
    agent: MoneyAgent
    secret: bytes
    wallet: AgentWallet | None = None
    payout_to: str | None = None
    operator: OperatorConfig | None = None

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _json(self, code: int, body: dict, extra_headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, code: int, text: str) -> None:
        raw = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _reserve(self) -> int:
        if self.operator:
            return self.operator.reserve_micros
        return PRICE_MICROS

    def _auto(self) -> bool:
        return True if self.operator is None else self.operator.auto_payout

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html = DASHBOARD.replace("$WALLET", self.wallet.address if self.wallet else "unset").replace(
                "$DEST", self.payout_to or "unset"
            )
            self._html(200, html)
            return
        if parsed.path == "/api/wallet":
            self._json(
                200,
                {
                    "agent_address": None if self.wallet is None else self.wallet.address,
                    "payout_address": self.payout_to,
                    "accepts_cards": False,
                    "accepts_private_keys": False,
                    "auto_payout": self._auto(),
                    "reserve_micros": self._reserve(),
                },
            )
            return
        if parsed.path == "/api/books":
            b = self.agent.ledger.books()
            self._json(
                200,
                {
                    "treasury_micros": b.treasury_micros,
                    "agent_micros": b.agent_micros,
                    "revenue_micros": b.revenue_micros,
                    "spend_micros": b.spend_micros,
                    "payout_micros": b.payout_micros,
                    "net_assets_micros": self.agent.ledger.net_assets(),
                    "session_spent_micros": b.session_spent_micros,
                },
            )
            return
        if parsed.path == "/api/activity":
            self._json(200, {"entries": self.agent.ledger.recent_entries(25)})
            return
        if parsed.path == INSIGHT_RESOURCE:
            qs = parse_qs(parsed.query)
            query = (qs.get("q") or ["untitled"])[0]
            payer = self.headers.get("X-Payer", "")
            invoice = self.headers.get("X-Invoice", "")
            proof = self.headers.get("X-Payment-Proof", "")
            if payer and invoice and proof:
                from money_agent.x402 import Challenge

                ch = Challenge(INSIGHT_RESOURCE, PRICE_MICROS, invoice)
                if verify_proof(self.secret, ch, payer, proof):
                    self._json(200, {"insight": self.agent.insight_for(query), "paid": True})
                    return
            ch = new_challenge()
            self._json(
                402,
                {"error": "Payment Required", "invoice": ch.invoice_id, "amount_micros": ch.amount_micros},
                extra_headers={"WWW-Authenticate": ch.header()},
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "object required"})
            return
        if parsed.path == "/v1/shift":
            n = int(body.get("customers", 3))
            n = max(1, min(n, 25))
            names = [f"buyer-{i}" for i in range(n)]
            report = self.agent.run_shift(names)
            self._json(200, report.__dict__)
            return
        if parsed.path == "/v1/turbo":
            ticks = int(body.get("ticks", 5))
            customers = int(body.get("customers", 3))
            report = run_turbo(
                self.agent,
                ticks=ticks,
                customers_per_tick=customers,
                payout_to=self.payout_to,
                reserve_micros=self._reserve(),
                auto_payout=self._auto(),
            )
            self._json(200, turbo_public(report))
            return
        if parsed.path == "/v1/sweep":
            if not self.payout_to:
                self._json(400, {"error": "set payout dest first"})
                return
            swept = sweep_excess(self.agent, self.payout_to, self._reserve())
            b = self.agent.ledger.books()
            self._json(
                200,
                {
                    "swept_micros": swept,
                    "paid_to": self.payout_to,
                    "treasury_micros": b.treasury_micros,
                    "payout_micros": b.payout_micros,
                    "broadcast": False,
                },
            )
            return
        if parsed.path == "/v1/proof":
            from money_agent.x402 import Challenge

            ch = Challenge(INSIGHT_RESOURCE, PRICE_MICROS, str(body["invoice"]))
            payer = str(body["payer"])
            self._json(200, {"proof": sign_proof(self.secret, ch, payer)})
            return
        if parsed.path == "/v1/payout":
            keys = {str(k).lower() for k in body}
            if keys & FORBIDDEN_PAYOUT_KEYS:
                self._json(400, {"error": "cards and secrets are rejected; send {amount_micros, to?}"})
                return
            dest = body.get("to") or self.payout_to
            if not dest:
                self._json(400, {"error": "set payout dest (public 0x address) first"})
                return
            try:
                dest = validate_payout_address(str(dest))
                if self.payout_to and dest != self.payout_to:
                    self._json(403, {"error": "destination is not the configured owner wallet"})
                    return
                amount = int(body["amount_micros"])
                self.agent.payout(amount, dest)
            except (WalletError, ValueError, KeyError) as exc:
                self._json(400, {"error": str(exc)})
                return
            b = self.agent.ledger.books()
            self._json(
                200,
                {
                    "paid_to": dest,
                    "amount_micros": amount,
                    "treasury_micros": b.treasury_micros,
                    "payout_micros": b.payout_micros,
                    "broadcast": False,
                },
            )
            return
        self._json(404, {"error": "not found"})


def make_server(
    agent: MoneyAgent,
    secret: bytes,
    host: str,
    port: int,
    *,
    wallet: AgentWallet | None = None,
    payout_to: str | None = None,
    operator: OperatorConfig | None = None,
) -> ThreadingHTTPServer:
    Handler.agent = agent
    Handler.secret = secret
    Handler.wallet = wallet
    Handler.payout_to = payout_to
    Handler.operator = operator
    return ThreadingHTTPServer((host, port), Handler)
