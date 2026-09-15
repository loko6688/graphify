"""CLI: python -m money_agent shift | serve | wallet | payout"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from money_agent.agent import MoneyAgent
from money_agent.config import load_config, require_payout_address, save_config
from money_agent.engine import run_go, run_turbo, turbo_public
from money_agent.ledger import Ledger
from money_agent.policy import SpendPolicy
from money_agent.server import make_server
from money_agent.ways import ways_payload
from money_agent.wallet import create_wallet, load_wallet, public_view, payout_chain
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS

DEFAULT_WALLET = Path.home() / ".money-agent" / "agent.wallet.json"
DEFAULT_DB = Path.home() / ".money-agent" / "ledger.sqlite"


def default_policy() -> SpendPolicy:
    return SpendPolicy(
        max_per_payment_micros=PRICE_MICROS,
        session_spend_cap_micros=PRICE_MICROS * 2,
        allowed_resources=frozenset({INSIGHT_RESOURCE}),
    )


def build_agent(db: Path) -> MoneyAgent:
    return MoneyAgent(Ledger(db), default_policy())


def _db(path: Path | None) -> Path:
    db = path or DEFAULT_DB
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
    p_dest.add_argument("--to", required=True, help="Solana base58, Tron T-addr, or 0x. Never a card or key.")
    p_dest.add_argument("--usdt", default=None, help="Optional extra USDT public address (Solana or Tron T-addr).")
    p_dest.add_argument("--reinvest-bps", type=int, default=None, help="0-9000. Default 4000 = 40% credits.")

    p_pay = sub.add_parser("payout", help="Send treasury micros to the configured owner address")
    p_pay.add_argument("--db", type=Path, required=True)
    p_pay.add_argument("--amount-micros", type=int, required=True)
    p_pay.add_argument("--to", default=None, help="override dest (Solana base58 or 0x). Never a card or key.")

    p_turbo = sub.add_parser("turbo", help="Run many shifts and auto-sweep excess to your 0x address")
    p_turbo.add_argument("--db", type=Path, default=None)
    p_turbo.add_argument("--ticks", type=int, default=8)
    p_turbo.add_argument("--customers", type=int, default=3)
    p_turbo.add_argument("--no-payout", action="store_true")
    p_turbo.add_argument("--reinvest-bps", type=int, default=None)

    p_go = sub.add_parser("go", help="Vollgas: several turbo rounds on the same ledger")
    p_go.add_argument("--db", type=Path, default=None)
    p_go.add_argument("--rounds", type=int, default=4)
    p_go.add_argument("--ticks", type=int, default=8)
    p_go.add_argument("--customers", type=int, default=4)
    p_go.add_argument("--no-payout", action="store_true")

    p_status = sub.add_parser("status", help="Show books, payout dest, and whether money is real")
    p_status.add_argument("--db", type=Path, default=None)

    p_ways = sub.add_parser("ways", help="List real rails (x402/Solana Pay). No fake yield.")

    args = parser.parse_args(argv)

    if args.cmd == "shift":
        agent = build_agent(_db(args.db))
        names = [f"buyer-{i}" for i in range(max(1, args.customers))]
        report = agent.run_shift(names)
        print(json.dumps(report.__dict__, indent=2))
        return 0

    if args.cmd == "status":
        cfg = load_config()
        db = args.db
        payload: dict = {
            "payout_address": cfg.payout_address,
            "usdt_address": cfg.usdt_address,
            "chain": cfg.chain,
            "reinvest_bps": cfg.reinvest_bps,
            "real_settlement": False,
            "min_500_eur_today": False,
            "note": "Ledger only. Real USDT/USDC needs a buyer who signs. No cards, no private keys.",
            "ways": ways_payload(cfg.payout_address, cfg.usdt_address)["ways"],
        }
        if db and db.exists():
            agent = build_agent(db)
            b = agent.ledger.books()
            payload.update(
                {
                    "treasury_micros": b.treasury_micros,
                    "agent_micros": b.agent_micros,
                    "credits_micros": b.credits_micros,
                    "payout_micros": b.payout_micros,
                    "revenue_micros": b.revenue_micros,
                    "net_assets_micros": agent.ledger.net_assets(),
                    "recent": agent.ledger.recent_entries(8),
                }
            )
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "ways":
        print(json.dumps(ways_payload(load_config().payout_address, load_config().usdt_address), indent=2))
        return 0

    if args.cmd == "wallet":
        if args.init:
            w = create_wallet(args.path)
        else:
            w = load_wallet(args.path)
        print(json.dumps(public_view(w), indent=2))
        return 0

    if args.cmd == "payout-dest":
        update = {"payout_address": args.to, "usdt_address": args.usdt or args.to}
        if args.reinvest_bps is not None:
            update["reinvest_bps"] = args.reinvest_bps
        cfg = save_config(update)
        print(
            json.dumps(
                {
                    "payout_address": cfg.payout_address,
                    "usdt_address": cfg.usdt_address,
                    "chain": cfg.chain,
                    "reinvest_bps": cfg.reinvest_bps,
                },
                indent=2,
            )
        )
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
                    "chain": payout_chain(dest),
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "turbo":
        cfg = load_config()
        dest = None if args.no_payout else cfg.payout_address
        reinvest = cfg.reinvest_bps if args.reinvest_bps is None else args.reinvest_bps
        agent = build_agent(_db(args.db))
        report = run_turbo(
            agent,
            ticks=args.ticks,
            customers_per_tick=args.customers,
            payout_to=dest,
            reserve_micros=cfg.reserve_micros,
            auto_payout=bool(dest) and not args.no_payout,
            reinvest_bps=reinvest,
        )
        print(json.dumps(turbo_public(report), indent=2))
        return 0

    if args.cmd == "go":
        cfg = load_config()
        dest = None if args.no_payout else cfg.payout_address
        agent = build_agent(_db(args.db))
        report = run_go(
            agent,
            rounds=args.rounds,
            ticks=args.ticks,
            customers_per_tick=args.customers,
            payout_to=dest,
            reserve_micros=cfg.reserve_micros,
            auto_payout=bool(dest) and not args.no_payout,
            reinvest_bps=cfg.reinvest_bps,
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
