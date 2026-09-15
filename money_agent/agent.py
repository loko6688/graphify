"""Money Agent loop: sell paid insight, optionally buy its own paid tool."""

from __future__ import annotations

from dataclasses import dataclass

from money_agent.ledger import Ledger
from money_agent.policy import PolicyError, SpendPolicy
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS


CATALOG = (
    "Graph community hubs concentrate change risk; charge for a path between two symbols.",
    "EXTRACTED edges are cheaper to trust than INFERRED; sell the delta as a paid brief.",
    "A god-node in GRAPH_REPORT.md is a product: wrap it as a one-question paid lookup.",
)


@dataclass
class ShiftReport:
    sales: int
    revenue_micros: int
    self_buys: int
    refused_spends: int
    treasury_micros: int
    agent_micros: int
    net_assets_micros: int


class MoneyAgent:
    def __init__(self, ledger: Ledger, policy: SpendPolicy, *, endowment_bps: int = 10_000) -> None:
        self.ledger = ledger
        self.policy = policy
        self.endowment_bps = endowment_bps

    def payout(self, amount_micros: int, dest_address: str) -> None:
        from money_agent.wallet import validate_payout_address

        dest = validate_payout_address(dest_address)
        if amount_micros <= 0:
            raise ValueError("amount must be positive")
        self.ledger.payout_to_owner(amount_micros, dest)

    def insight_for(self, query: str) -> str:
        pick = CATALOG[sum(ord(c) for c in query) % len(CATALOG)]
        return f"Paid insight for {query!r}: {pick}"

    def sell_to_customer(self, customer_id: str, query: str) -> str:
        customer = f"customer:{customer_id}"
        self.ledger.fund_customer(customer, PRICE_MICROS, memo=f"buyer {customer_id}")
        self.ledger.collect_sale(customer, PRICE_MICROS, memo=f"sale {query}")
        cut = (PRICE_MICROS * self.endowment_bps) // 10_000
        if cut > 0:
            self.ledger.endowment_to_agent(cut, memo="commission")
        return self.insight_for(query)

    def maybe_buy_own_tool(self) -> bool:
        books = self.ledger.books()
        amount = min(PRICE_MICROS, self.policy.max_per_payment_micros, books.agent_micros)
        if amount <= 0:
            return False
        try:
            self.policy.authorize(
                amount_micros=amount,
                resource=INSIGHT_RESOURCE,
                session_spent_micros=books.session_spent_micros,
            )
        except PolicyError:
            return False
        try:
            self.ledger.agent_spend(amount, memo="self-hosted research")
        except ValueError:
            return False
        return True

    def run_shift(self, customers: list[str]) -> ShiftReport:
        sales = 0
        self_buys = 0
        refused = 0
        for i, cid in enumerate(customers):
            self.sell_to_customer(cid, query=f"q-{i}")
            sales += 1
            if self.maybe_buy_own_tool():
                self_buys += 1
            else:
                refused += 1
        books = self.ledger.books()
        return ShiftReport(
            sales=sales,
            revenue_micros=books.revenue_micros,
            self_buys=self_buys,
            refused_spends=refused,
            treasury_micros=books.treasury_micros,
            agent_micros=books.agent_micros,
            net_assets_micros=self.ledger.net_assets(),
        )
