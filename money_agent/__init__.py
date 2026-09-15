"""Money Agent: bounded x402-style merchant + buyer with an honest ledger.

This agent can *earn* when an external payer buys a paid resource, and can
*spend* from an operator-capped operating budget. Paying itself does not
print money: internal transfers cancel in the books.
"""

__version__ = "0.1.0"
