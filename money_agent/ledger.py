"""Integer-micros double-entry ledger. No floats. Agent cannot mint."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

TREASURY = "treasury"
AGENT = "agent"
MARKET = "market"  # external world. Credits here are real inflows.


@dataclass(frozen=True)
class Books:
    treasury_micros: int
    agent_micros: int
    revenue_micros: int
    spend_micros: int
    payout_micros: int
    net_profit_micros: int
    session_spent_micros: int


class Ledger:
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                name TEXT PRIMARY KEY,
                balance_micros INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                debit TEXT NOT NULL,
                credit TEXT NOT NULL,
                amount_micros INTEGER NOT NULL,
                kind TEXT NOT NULL,
                memo TEXT NOT NULL
            );
            """
        )
        for name in (TREASURY, AGENT, MARKET):
            self._conn.execute(
                "INSERT OR IGNORE INTO accounts(name, balance_micros) VALUES (?, 0)",
                (name,),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _balance(self, name: str) -> int:
        row = self._conn.execute(
            "SELECT balance_micros FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO accounts(name, balance_micros) VALUES (?, 0)", (name,)
            )
            return 0
        return int(row[0])

    def _transfer(self, debit: str, credit: str, amount: int, kind: str, memo: str) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if debit == credit:
            raise ValueError("debit and credit must differ")
        src = self._balance(debit)
        self._balance(credit)
        if debit != MARKET and src < amount:
            raise ValueError(f"insufficient funds in {debit}")
        self._conn.execute(
            "UPDATE accounts SET balance_micros = balance_micros - ? WHERE name = ?",
            (amount, debit),
        )
        self._conn.execute(
            "UPDATE accounts SET balance_micros = balance_micros + ? WHERE name = ?",
            (amount, credit),
        )
        self._conn.execute(
            "INSERT INTO entries(debit, credit, amount_micros, kind, memo) VALUES (?,?,?,?,?)",
            (debit, credit, amount, kind, memo),
        )

    def fund_customer(self, customer: str, amount: int, memo: str = "market funding") -> None:
        """External money enters the system. Only MARKET may be overdrawn (mint)."""
        with self._lock:
            if not customer.startswith("customer:"):
                raise ValueError("customers must be named customer:<id>")
            self._transfer(MARKET, customer, amount, "inflow", memo)
            self._conn.commit()

    def collect_sale(self, customer: str, amount: int, memo: str) -> None:
        with self._lock:
            self._transfer(customer, TREASURY, amount, "revenue", memo)
            self._conn.commit()

    def endowment_to_agent(self, amount: int, memo: str = "operating endowment") -> None:
        """Treasury funds the agent. Internal. Net profit unchanged."""
        with self._lock:
            self._transfer(TREASURY, AGENT, amount, "endowment", memo)
            self._conn.commit()

    def agent_spend(self, amount: int, memo: str) -> None:
        """Agent pays treasury (self-hosted paid tool). Internal. Net profit unchanged."""
        with self._lock:
            self._transfer(AGENT, TREASURY, amount, "cogs", memo)
            self._conn.commit()

    def payout_to_owner(self, amount: int, dest_address: str, memo: str = "owner payout") -> None:
        """Treasury leaves the agent to the operator's external wallet (MARKET)."""
        with self._lock:
            self._transfer(TREASURY, MARKET, amount, "payout", f"{memo} {dest_address}")
            self._conn.commit()

    def books(self) -> Books:
        with self._lock:
            rev = self._conn.execute(
                "SELECT COALESCE(SUM(amount_micros),0) FROM entries WHERE kind = 'revenue'"
            ).fetchone()[0]
            spend = self._conn.execute(
                "SELECT COALESCE(SUM(amount_micros),0) FROM entries WHERE kind = 'cogs'"
            ).fetchone()[0]
            session = self._conn.execute(
                "SELECT COALESCE(SUM(amount_micros),0) FROM entries WHERE kind = 'cogs'"
            ).fetchone()[0]
            inflow = self._conn.execute(
                "SELECT COALESCE(SUM(amount_micros),0) FROM entries WHERE kind = 'inflow'"
            ).fetchone()[0]
            payout = self._conn.execute(
                "SELECT COALESCE(SUM(amount_micros),0) FROM entries WHERE kind = 'payout'"
            ).fetchone()[0]
            return Books(
                treasury_micros=self._balance(TREASURY),
                agent_micros=self._balance(AGENT),
                revenue_micros=int(rev),
                spend_micros=int(spend),
                payout_micros=int(payout),
                net_profit_micros=int(inflow) - int(payout),
                session_spent_micros=int(session),
            )

    def recent_entries(self, limit: int = 20) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, ts, debit, credit, amount_micros, kind, memo
                FROM entries ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "ts": r[1],
                "debit": r[2],
                "credit": r[3],
                "amount_micros": r[4],
                "kind": r[5],
                "memo": r[6],
            }
            for r in rows
        ]

    def net_assets(self) -> int:
        """Treasury + agent + customers. Equals market inflows minus payouts."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(balance_micros),0) FROM accounts WHERE name != ?",
                (MARKET,),
            ).fetchone()
            return int(row[0])
