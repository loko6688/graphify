"""Spend policy. The model never sets these numbers; code does."""

from __future__ import annotations

from dataclasses import dataclass


class PolicyError(ValueError):
    """Payment refused by policy before any ledger write."""


@dataclass(frozen=True)
class SpendPolicy:
    max_per_payment_micros: int
    session_spend_cap_micros: int
    allowed_resources: frozenset[str]

    def authorize(self, *, amount_micros: int, resource: str, session_spent_micros: int) -> None:
        if amount_micros <= 0:
            raise PolicyError("amount must be positive")
        if amount_micros > self.max_per_payment_micros:
            raise PolicyError("over per-payment cap")
        if session_spent_micros + amount_micros > self.session_spend_cap_micros:
            raise PolicyError("over session spend cap")
        if resource not in self.allowed_resources:
            raise PolicyError("resource not allowlisted")
