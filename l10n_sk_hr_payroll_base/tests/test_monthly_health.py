# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from decimal import Decimal

from odoo.tests import BaseCase, tagged

from ..monthly_health import FIELDS, health_policy, health_total, monthly_health


@tagged("post_install", "-at_install")
class TestMonthlyHealth(BaseCase):
    def policy(self, **extra):
        return health_policy(**dict({
            "employee_rate": 5, "employer_rate": 11, "op_maximum": 380,
            "op_phaseout_end": 570, "op_days": 30, "month_days": 30,
            "minimum_base": "284.13", "minimum_days": 30, "apply_op": True,
            "minimum_exempt": False, "exempt": False,
        }, **extra))

    def split(self, incomes, **extra):
        policy, rows = self.policy(**extra), []
        for income in incomes:
            delta = monthly_health(income=income, policy=policy, previous=rows)
            rows.append({key: delta[key] for key in FIELDS})
        for key in FIELDS:
            self.assertEqual(sum(row[key] for row in rows), health_total(sum(incomes), policy)[key])
        return rows

    def test_200_plus_200_refunds_prior_minimum_without_rewriting_it(self):
        first, second = self.split([200, 200])
        self.assertEqual(first["topup"], Decimal("23.45"))
        self.assertEqual((second["op"], second["base"], second["employee"], second["employer"], second["topup"]),
                         (Decimal(140), Decimal(60), Decimal(3), Decimal(22), Decimal("-23.45")))

    def test_250_plus_250_has_a_negative_op_fragment_and_valid_monthly_op(self):
        first, second = self.split([250, 250])
        self.assertEqual((first["op"], second["op"]), (Decimal(250), Decimal(-110)))
        self.assertEqual(second["base"], Decimal(360))

    def test_third_payment_crossing_op_threshold_recaptures_the_allowance(self):
        rows = self.split([200, 200, 200])
        self.assertEqual(rows[-1]["op"], Decimal(-340))
        self.assertEqual(sum(row["op"] for row in rows), 0)

    def test_2027_dated_minimum_leaves_twenty_three_cents_topup(self):
        first, second = self.split([200, 200], minimum_base="295.22")
        self.assertEqual(first["topup"], Decimal("25.23"))
        self.assertEqual(second["topup"], Decimal(-25))

    def test_disability_keeps_halved_rates_and_no_minimum(self):
        rows = self.split([200, 200], employee_rate="2.5", employer_rate="5.5", minimum_exempt=True)
        self.assertEqual(sum(row["employee"] for row in rows), Decimal("1.5"))
        self.assertEqual(sum(row["employer"] for row in rows), Decimal(22))

    def test_benefit_reduces_minimum_but_not_op_employment_days(self):
        rows = self.split([200, 200], minimum_days=10)
        self.assertEqual(sum(row["op"] for row in rows), Decimal(340))
        self.assertEqual(sum(row["topup"] for row in rows), 0)

    def test_2n_days_prorate_op_and_minimum_once(self):
        rows = self.split([200, 200], minimum_days=10, op_days=10)
        self.assertEqual(sum(row["op"] for row in rows), Decimal("113.34"))

    def test_excluded_income_records_zero_assessments_without_new_allowance(self):
        rows = self.split([200, 200], exempt=True, apply_op=False, minimum_exempt=True)
        self.assertTrue(all(not row[key] for row in rows for key in FIELDS - {"income"}))

    def test_signed_fragment_is_not_a_valid_orphaned_standalone_source(self):
        first, second = self.split([200, 200])
        with self.assertRaisesRegex(ValueError, "explicit source correction"):
            monthly_health(income=200, policy=self.policy(), previous=[second])
        self.assertEqual(first["topup"], Decimal("23.45"))

    def test_custom_prior_amount_is_not_overridden_with_an_invented_canonical_amount(self):
        first = self.split([200])[0]
        first["employee"] += Decimal(1)
        with self.assertRaisesRegex(ValueError, "explicit source correction"):
            monthly_health(income=200, policy=self.policy(), previous=[first])
