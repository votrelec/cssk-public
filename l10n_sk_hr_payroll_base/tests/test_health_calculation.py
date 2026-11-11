# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from decimal import Decimal

from odoo.tests import BaseCase, tagged

from ..health_calculation import monthly_minimum, monthly_op


@tagged("post_install", "-at_install")
class TestHealthCalculation(BaseCase):
    def test_op_cent_boundaries_and_distinct_total_eligible_income(self):
        cases = (
            (200, 200, 30, 30, "200"),
            (200, 200, 1, 30, "6.67"),
            (200, 200, 1, 31, "6.46"),
            (500, 200, 30, 30, "140"),
            (500, 100, 30, 30, "100"),
            (570, 200, 30, 30, "0"),
            (569.99, 569.99, 1, 30, "0.01"),
            (380, 380, 1, 29, "13.11"),
            (380, 380, 1, 28, "13.58"),
            (200, 200, 0, 30, "0"),
            (-200, 0, 30, 30, "0"),
        )
        for total, eligible, days, month_days, expected in cases:
            with self.subTest(
                total=total, eligible=eligible, days=days, month=month_days
            ):
                self.assertEqual(
                    monthly_op(total, eligible, 380, 570, days, month_days),
                    Decimal(expected),
                )

    def test_minimum_floors_components_then_prorates_once(self):
        self.assertEqual(monthly_minimum(284.13, 5, 11, 30, 30), Decimal("45.45"))
        self.assertEqual(monthly_minimum(284.13, 5, 11, 15, 30), Decimal("22.72"))
        self.assertEqual(monthly_minimum(284.13, 5, 11, 29, 30), Decimal("43.93"))
        self.assertEqual(monthly_minimum(284.13, 5, 11, 0, 30), 0)

    def test_invalid_inputs_cannot_silently_create_a_statutory_amount(self):
        for values in (
            (200, 201, 380, 570, 30, 30),
            (200, 200, 380, 380, 30, 30),
            (200, 200, 380, 570, 31, 30),
            (True, 0, 380, 570, 30, 30),
            ("NaN", 0, 380, 570, 30, 30),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                monthly_op(*values)
