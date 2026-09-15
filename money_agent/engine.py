"""Multi-tick earn loop with optional treasury sweep to the owner address."""

from __future__ import annotations

from dataclasses import dataclass, field

from money_agent.agent import MoneyAgent, ShiftReport


@dataclass
class TickResult:
    shift: ShiftReport
    swept_micros: int


@dataclass
class TurboReport:
    ticks: int
    sales: int
    payouts: int
    swept_micros: int
    treasury_micros: int
    agent_micros: int
    payout_micros: int
    net_assets_micros: int
    paid_to: str | None = None
    chain: str | None = None
    real_settlement: bool = False
    ticks_detail: list[TickResult] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "ticks": self.ticks,
            "sales": self.sales,
            "payouts": self.payouts,
            "swept_micros": self.swept_micros,
            "treasury_micros": self.treasury_micros,
            "agent_micros": self.agent_micros,
            "payout_micros": self.payout_micros,
            "net_assets_micros": self.net_assets_micros,
            "paid_to": self.paid_to,
            "chain": self.chain,
            "real_settlement": self.real_settlement,
        }


def sweep_excess(agent: MoneyAgent, dest: str | None, reserve_micros: int) -> int:
    if not dest:
        return 0
    books = agent.ledger.books()
    excess = books.treasury_micros - reserve_micros
    if excess <= 0:
        return 0
    agent.payout(excess, dest)
    return excess


def run_turbo(
    agent: MoneyAgent,
    *,
    ticks: int,
    customers_per_tick: int,
    payout_to: str | None,
    reserve_micros: int,
    auto_payout: bool,
) -> TurboReport:
    ticks = max(1, min(ticks, 50))
    customers_per_tick = max(1, min(customers_per_tick, 25))
    sales = 0
    payouts = 0
    swept = 0
    details: list[TickResult] = []
    for t in range(ticks):
        names = [f"t{t}-b{i}" for i in range(customers_per_tick)]
        report = agent.run_shift(names)
        sales += report.sales
        swept_now = 0
        if auto_payout:
            swept_now = sweep_excess(agent, payout_to, reserve_micros)
            if swept_now:
                payouts += 1
                swept += swept_now
        details.append(TickResult(shift=report, swept_micros=swept_now))
    books = agent.ledger.books()
    chain = None
    if payout_to:
        from money_agent.wallet import payout_chain

        chain = payout_chain(payout_to)
    return TurboReport(
        ticks=ticks,
        sales=sales,
        payouts=payouts,
        swept_micros=swept,
        treasury_micros=books.treasury_micros,
        agent_micros=books.agent_micros,
        payout_micros=books.payout_micros,
        net_assets_micros=agent.ledger.net_assets(),
        paid_to=payout_to,
        chain=chain,
        real_settlement=False,
        ticks_detail=details,
    )


def turbo_public(report: TurboReport) -> dict:
    body = report.as_json()
    body["ticks_detail"] = [
        {"sales": d.shift.sales, "treasury_micros": d.shift.treasury_micros, "swept_micros": d.swept_micros}
        for d in report.ticks_detail
    ]
    return body
