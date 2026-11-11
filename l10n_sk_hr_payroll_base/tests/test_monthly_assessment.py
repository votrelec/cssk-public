# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from decimal import Decimal
from odoo.tests import BaseCase, tagged

from ..monthly_assessment import monthly_assessment


@tagged("post_install", "-at_install")
class TestMonthlyAssessment(BaseCase):
    def test_oop_is_used_once_before_the_cap(self):
        first = monthly_assessment(income=200, rate=4, maximum=16764,
                                   deduction=200, previous=[])
        second = monthly_assessment(income=200, rate=4, maximum=16764,
                                    deduction=200, previous=[dict(first, income=200, rate=4)])
        self.assertEqual(first, {"base": 0, "amount": 0})
        self.assertEqual(second, {"base": 200, "amount": 8})

    def test_cap_is_not_reused_by_a_later_payment(self):
        first = monthly_assessment(income=17100, rate=4, maximum=16764,
                                   deduction=200, previous=[])
        second = monthly_assessment(income=500, rate=4, maximum=16764,
                                    deduction=200, previous=[dict(first, income=17100, rate=4)])
        self.assertEqual(first["amount"], Decimal("670.56"))
        self.assertEqual(second, {"base": 0, "amount": 0})

    def test_monthly_rate_bucket_retains_cent_remainders(self):
        first = monthly_assessment(income="0.25", rate="1.4", maximum=16764,
                                   deduction=0, previous=[])
        second = monthly_assessment(income="0.50", rate="1.4", maximum=16764,
                                    deduction=0, previous=[dict(first, income="0.25", rate="1.4")])
        self.assertEqual(first["amount"], 0)
        self.assertEqual(second["amount"], Decimal("0.01"))

    def test_accident_is_uncapped_and_keeps_its_income(self):
        first = monthly_assessment(income=20000, rate="0.8", maximum=None,
                                   deduction=0, previous=[])
        second = monthly_assessment(income=1000, rate="0.8", maximum=None,
                                    deduction=0, previous=[dict(first, income=20000, rate="0.8")])
        self.assertEqual(first["amount"], 160)
        self.assertEqual(second, {"base": 1000, "amount": 8})

    def test_rate_change_does_not_reprice_previous_income(self):
        result = monthly_assessment(income=100, rate=1, maximum=16764, deduction=0,
                                    previous=[{"income": 100, "base": 100,
                                               "rate": "0.5", "amount": "0.5"}])
        self.assertEqual(result, {"base": 100, "amount": 1})

    def test_incomplete_or_overcharged_sources_are_not_guessed(self):
        for row in ({"amount": 8}, {"income": 200, "base": 200, "rate": 4, "amount": 8}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                monthly_assessment(income=0, rate=4, maximum=16764,
                                   deduction=200, previous=[row])
