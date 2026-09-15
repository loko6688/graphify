"""CLI: python -m money_agent shift | serve | wallet | payout"""

from __future__ import annotations

import argparse
import json
import secrets
import tempfile
from pathlib import Path

from money_agent.agent import MoneyAgent
from money_agent.config import load_config, require_payout_address, save_payout_address
from money_agent.engine import run_turbo, turbo_public
from money_agent.ledger import Ledger
from money_agent.policy import SpendPolicy
from money_agent.server import make_server
from money_agent.wallet import create_wallet, load_wallet, public_view
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS

DEFAULT_WALLET = Path.home() / ".money-agent" / "agent.wallet.json"


def default_policy() -> SpendPolicy:
    return SpendPolicy(
        max_per_payment_micros=PRICE_MICROS,
        session_spend_cap_micros=PRICE_MICROS * 2,
        allowed_resources=frozenset({INSIGHT_RESOURCE}),
    )


def build_agent(db: Path) -> MoneyAgent:
    return MoneyAgent(Ledger(db), default_policy())


def _db(path: Path | None) -> Path:
    db = path or Path(tempfile.mkdtemp()) / "money.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="money-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_shift = sub.add_parser("shift", help="Run a simulated earning shift")
    p_shift.add_argument("--customers", type=int, default=5)
    p_shift.add_argument("--db", type=Path, default=None)

    p_serve = sub.add_parser("serve", help="HTTP dashboard + 402 merchant")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--db", type=Path, default=None)
    p_serve.add_argument("--wallet", type=Path, default=DEFAULT_WALLET)

    p_wallet = sub.add_parser("wallet", help="Create or show the agent keystore (address only)")
    p_wallet.add_argument("--path", type=Path, default=DEFAULT_WALLET)
    p_wallet.add_argument("--init", action="store_true")

    p_dest = sub.add_parser("payout-dest", help="Save YOUR public wallet as payout destination")
    p_dest.add_argument("--to", required=True, help="0x + 40 hex. Never a card or private key.")

    p_pay = sub.add_parser("payout", help="Send treasury micros to the configured owner address")
    p_pay.add_argument("--db", type=Path, required=True)
    p_pay.add_argument("--amount-micros", type=int, required=True)
    p_pay.add_argument("--to", default=None, help="override destination (must still be a public 0x address)")

    p_turbo = sub.add_parser("turbo", help="Run many shifts and auto-sweep excess to your 0x address")
    p_turbo.add_argument("--db", type=Path, required=True)
    p_turbo.add_argument("--ticks", type=int, default=8)
    p_turbo.add_argument("--customers", type=int, default=3)
    p_turbo.add_argument("--no-payout", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "shift":
        agent = build_agent(_db(args.db))
        names = [f"buyer-{i}" for i in range(max(1, args.customers))]
        report = agent.run_shift(names)
        print(json.dumps(report.__dict__, indent=2))
        return 0

    if args.cmd == "wallet":
        if args.init:
            w = create_wallet(args.path)
        else:
            w = load_wallet(args.path)
        print(json.dumps(public_view(w), indent=2))
        return 0

    if args.cmd == "payout-dest":
        cfg = save_payout_address(args.to)
        print(json.dumps({"payout_address": cfg.payout_address}, indent=2))
        return 0

    if args.cmd == "payout":
        dest = args.to or require_payout_address(load_config())
        agent = build_agent(args.db)
        agent.payout(args.amount_micros, dest)
        books = agent.ledger.books()
        print(
            json.dumps(
                {
                    "paid_to": dest,
                    "amount_micros": args.amount_micros,
                    "treasury_micros": books.treasury_micros,
                    "payout_micros": books.payout_micros,
                    "net_assets_micros": agent.ledger.net_assets(),
                    "chain": "ledger-only (wire a wallet signer to broadcast)",
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "turbo":
        cfg = load_config()
        dest = None if args.no_payout else cfg.payout_address
        agent = build_agent(args.db)
        report = run_turbo(
            agent,
            ticks=args.ticks,
            customers_per_tick=args.customers,
            payout_to=dest,
            reserve_micros=cfg.reserve_micros,
            auto_payout=bool(dest) and not args.no_payout,
        )
        print(json.dumps(turbo_public(report), indent=2))
        return 0

    db = _db(args.db)
    wallet_path = args.wallet
    if not wallet_path.exists():
        create_wallet(wallet_path)
    wallet = load_wallet(wallet_path)
    payout_to = load_config().payout_address
    operator = load_config()
    httpd = make_server(
        build_agent(db),
        secrets.token_bytes(32),
        args.host,
        args.port,
        wallet=wallet,
        payout_to=payout_to,
        operator=operator,
    )
    print(f"Money Agent on http://{args.host}:{args.port}  ledger={db}")
    print(f"agent wallet {wallet.address}  payout_to={payout_to or 'unset'}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
