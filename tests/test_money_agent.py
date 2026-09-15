from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from money_agent.agent import MoneyAgent
from money_agent.ledger import AGENT, TREASURY, Ledger
from money_agent.policy import PolicyError, SpendPolicy
from money_agent.server import make_server
from money_agent.x402 import INSIGHT_RESOURCE, PRICE_MICROS, Challenge, sign_proof
from money_agent.__main__ import default_policy, main


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "l.sqlite")

    def tearDown(self) -> None:
        self.ledger.close()
        self.tmp.cleanup()

    def test_self_pay_does_not_increase_net_assets(self) -> None:
        self.ledger.fund_customer("customer:a", 100)
        self.ledger.collect_sale("customer:a", 100, "sale")
        before = self.ledger.net_assets()
        self.ledger.endowment_to_agent(40)
        self.ledger.agent_spend(10, "self buy")
        self.assertEqual(self.ledger.net_assets(), before)
        self.assertEqual(self.ledger._balance(TREASURY) + self.ledger._balance(AGENT), before)

    def test_agent_cannot_mint(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.agent_spend(1, "no money")


class PolicyTests(unittest.TestCase):
    def test_caps(self) -> None:
        p = SpendPolicy(10, 15, frozenset({INSIGHT_RESOURCE}))
        p.authorize(amount_micros=10, resource=INSIGHT_RESOURCE, session_spent_micros=0)
        with self.assertRaises(PolicyError):
            p.authorize(amount_micros=11, resource=INSIGHT_RESOURCE, session_spent_micros=0)
        with self.assertRaises(PolicyError):
            p.authorize(amount_micros=10, resource=INSIGHT_RESOURCE, session_spent_micros=6)
        with self.assertRaises(PolicyError):
            p.authorize(amount_micros=10, resource="/evil", session_spent_micros=0)


class ShiftTests(unittest.TestCase):
    def test_shift_earns_external_money_and_session_cap_stops_self_buy(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        ledger = Ledger(Path(tmp.name) / "l.sqlite")
        policy = SpendPolicy(
            max_per_payment_micros=PRICE_MICROS,
            session_spend_cap_micros=PRICE_MICROS,  # only one self-buy
            allowed_resources=frozenset({INSIGHT_RESOURCE}),
        )
        agent = MoneyAgent(ledger, policy)
        report = agent.run_shift(["x", "y", "z"])
        self.assertEqual(report.sales, 3)
        self.assertEqual(report.revenue_micros, 3 * PRICE_MICROS)
        self.assertEqual(report.net_assets_micros, 3 * PRICE_MICROS)
        self.assertEqual(report.self_buys, 1)
        self.assertEqual(report.refused_spends, 2)
        ledger.close()
        tmp.cleanup()


class HttpTests(unittest.TestCase):
    def test_402_then_paid_insight(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        ledger = Ledger(Path(tmp.name) / "l.sqlite")
        agent = MoneyAgent(ledger, default_policy())
        secret = b"unit-test-secret-unit-test-secret"
        httpd = make_server(agent, secret, "127.0.0.1", 0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_address[1]
        try:
            try:
                urlopen(f"http://127.0.0.1:{port}/v1/insight?q=hubs", timeout=5)
                self.fail("expected 402")
            except HTTPError as exc:
                self.assertEqual(exc.code, 402)
                body = json.loads(exc.read().decode())
                self.assertIn("invoice", body)
            books = json.loads(urlopen(f"http://127.0.0.1:{port}/api/books", timeout=5).read())
            self.assertEqual(books["revenue_micros"], 0)
            shift = json.loads(
                urlopen(
                    Request(
                        f"http://127.0.0.1:{port}/v1/shift",
                        data=b'{"customers":2}',
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                ).read()
            )
            self.assertEqual(shift["sales"], 2)
            self.assertEqual(shift["net_assets_micros"], 2 * PRICE_MICROS)
            home = urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
            self.assertIn("Money Agent", home)
            invoice = "abcd" * 8
            proof = sign_proof(secret, Challenge(INSIGHT_RESOURCE, PRICE_MICROS, invoice), "alice")
            req = Request(
                f"http://127.0.0.1:{port}/v1/insight?q=hubs",
                headers={
                    "X-Payer": "alice",
                    "X-Invoice": invoice,
                    "X-Payment-Proof": proof,
                },
            )
            paid = json.loads(urlopen(req, timeout=5).read())
            self.assertTrue(paid["paid"])
            self.assertIn("Paid insight", paid["insight"])
        finally:
            httpd.shutdown()
            ledger.close()
            tmp.cleanup()


class CliTests(unittest.TestCase):
    def test_shift_cli(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        db = Path(tmp.name) / "m.sqlite"
        code = main(["shift", "--customers", "1", "--db", str(db)])
        self.assertEqual(code, 0)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
