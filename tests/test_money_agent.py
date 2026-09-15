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
from money_agent.wallet import WalletError, create_wallet, public_view, validate_payout_address
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


    def test_payout_leaves_the_books(self) -> None:
        self.ledger.fund_customer("customer:a", 100)
        self.ledger.collect_sale("customer:a", 100, "sale")
        self.assertEqual(self.ledger.net_assets(), 100)
        self.ledger.payout_to_owner(40, "0x" + "ab" * 20)
        self.assertEqual(self.ledger.net_assets(), 60)
        self.assertEqual(self.ledger.books().payout_micros, 40)


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


class WalletTests(unittest.TestCase):
    def test_create_and_refuse_cards_and_keys(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "agent.wallet.json"
        w = create_wallet(path)
        self.assertTrue(w.address.startswith("0x"))
        self.assertEqual(len(w.address), 42)
        view = public_view(w)
        self.assertNotIn("secret", json.dumps(view))
        with self.assertRaises(WalletError):
            validate_payout_address("4111111111111111")
        with self.assertRaises(WalletError):
            validate_payout_address("ab" * 32)
        good = "0x" + "11" * 20
        self.assertEqual(validate_payout_address(good), good)
        tmp.cleanup()


class HttpPayoutTests(unittest.TestCase):
    def test_payout_and_card_rejection(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        ledger = Ledger(Path(tmp.name) / "l.sqlite")
        dest = "0x" + "22" * 20
        agent = MoneyAgent(ledger, default_policy())
        httpd = make_server(
            agent,
            b"unit-test-secret-unit-test-secret",
            "127.0.0.1",
            0,
            payout_to=dest,
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_address[1]
        try:
            urlopen(
                Request(
                    f"http://127.0.0.1:{port}/v1/shift",
                    data=b'{"customers":2}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=5,
            )
            try:
                urlopen(
                    Request(
                        f"http://127.0.0.1:{port}/v1/payout",
                        data=b'{"card":"4111111111111111","amount_micros":1}',
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                self.fail("expected card rejection")
            except HTTPError as exc:
                self.assertEqual(exc.code, 400)
            before = json.loads(urlopen(f"http://127.0.0.1:{port}/api/books", timeout=5).read())
            paid = json.loads(
                urlopen(
                    Request(
                        f"http://127.0.0.1:{port}/v1/payout",
                        data=b'{"amount_micros":50000}',
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                ).read()
            )
            self.assertEqual(paid["paid_to"], dest)
            self.assertFalse(paid["broadcast"])
            after = json.loads(urlopen(f"http://127.0.0.1:{port}/api/books", timeout=5).read())
            self.assertEqual(after["payout_micros"], 50000)
            self.assertEqual(after["net_assets_micros"], before["net_assets_micros"] - 50000)
            wallet = json.loads(urlopen(f"http://127.0.0.1:{port}/api/wallet", timeout=5).read())
            self.assertFalse(wallet["accepts_cards"])
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

    def test_wallet_cli_init(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "w.json"
        code = main(["wallet", "--init", "--path", str(path)])
        self.assertEqual(code, 0)
        dest = "0x" + "33" * 20
        cfg = Path(tmp.name) / "cfg.json"
        import os

        os.environ["MONEY_AGENT_CONFIG"] = str(cfg)
        try:
            code = main(["payout-dest", "--to", dest])
            self.assertEqual(code, 0)
        finally:
            os.environ.pop("MONEY_AGENT_CONFIG", None)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
