"""CLI: python -m money_agent shift | serve"""

from __future__ import annotations

import argparse
import json
import secrets
import tempfile
from pathlib import Path

from money_agent.agent import MoneyAgent
from money_agent.ledger import Ledger
from money_agent.policy import SpendPolicy
from money_agent.server import make_server
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS


def default_policy() -> SpendPolicy:
    return SpendPolicy(
        max_per_payment_micros=PRICE_MICROS,
        session_spend_cap_micros=PRICE_MICROS * 2,
        allowed_resources=frozenset({INSIGHT_RESOURCE}),
    )


def build_agent(db: Path) -> MoneyAgent:
    return MoneyAgent(Ledger(db), default_policy())


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
    args = parser.parse_args(argv)

    if args.cmd == "shift":
        db = args.db or Path(tempfile.mkdtemp()) / "money.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        agent = build_agent(db)
        names = [f"buyer-{i}" for i in range(max(1, args.customers))]
        report = agent.run_shift(names)
        print(json.dumps(report.__dict__, indent=2))
        print(f"ledger: {db}")
        return 0

    db = args.db or Path(tempfile.mkdtemp()) / "money.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    httpd = make_server(build_agent(db), secrets.token_bytes(32), args.host, args.port)
    print(f"Money Agent on http://{args.host}:{args.port}  ledger={db}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
