# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from copy import deepcopy
from decimal import Decimal

from odoo.tests import BaseCase, tagged

from ..assessment514 import merge_assessment_rows, row_from_assessments


@tagged("post_install", "-at_install")
class TestHealthAssessment514(BaseCase):
    def setUp(self):
        super().setUp()
        self.health = {
            "exempt": False,
            "disabled": False,
            "minimum_opt_out": False,
            "minimum_exempt": False,
        }
        self.records = [
            {
                "fund": "health", "side": "employee", "base": "0", "rate": "5",
                "amount": "11.73", "facts": {"income": "200", "op": "200", "topup": "11.73"},
            },
            {
                "fund": "health", "side": "employer", "base": "200", "rate": "11",
                "amount": "22", "facts": {},
            },
        ]

    def row(self, **extra):
        return row_from_assessments(
            self.records, self.health, op_eligible=extra.pop("op_eligible", True),
            days=extra.pop("days", 30), **extra,
        )

    def test_actual_op_and_topup_are_separate_from_ordinary_premium(self):
        before = deepcopy(self.records)
        row = self.row()
        self.assertEqual(row["employee"], 0)
        self.assertEqual(row["topup"], Decimal("11.73"))
        self.assertEqual(row["total"], Decimal("33.73"))
        self.assertEqual(row["base"], 0)
        self.assertEqual(row["op"], 200)
        self.assertEqual(row["rate_employee"], 5)
        self.assertTrue(row["premium_assessed"])
        self.assertEqual(self.records, before)

    def test_base_rounding_does_not_floor_income_op_or_actual_premiums(self):
        self.records[0].update(base="100.019999", amount="5.009999")
        self.records[0]["facts"] = {"income": "100.019999", "op": "0.009999"}
        self.records[1].update(base="100.019999", amount="11.009999")
        row = self.row()
        self.assertEqual(row["base"], Decimal("100.01"))
        self.assertEqual(row["income"], Decimal("100.02"))
        self.assertEqual(row["op"], Decimal(".01"))
        self.assertEqual(row["employee"], Decimal("5.01"))
        self.assertIsNone(row["shorttime_base"])

    def test_native_refund_direction_is_applied_exactly_once(self):
        positive = self.row()
        negative = self.row(direction=-1)
        for key in ("income", "base", "employer_base", "employee", "employer", "topup", "op", "total"):
            self.assertEqual(negative[key], -positive[key])
        self.assertEqual(negative["rate_employee"], positive["rate_employee"])

    def test_excluded_nonzero_assessments_are_not_silently_filtered(self):
        self.health["exempt"] = True
        with self.assertRaisesRegex(ValueError, "nonzero payroll"):
            self.row()
        for record in self.records:
            record.update(base="0", amount="0")
        self.assertIsNone(self.row())

    def test_full_month_exemption_and_opt_out_both_require_zero_topup(self):
        for key in ("minimum_opt_out", "minimum_exempt"):
            with self.subTest(key=key):
                self.health[key] = True
                with self.assertRaisesRegex(ValueError, "nonzero top-up"):
                    self.row()
                self.health[key] = False
        self.records[0].update(amount="0", facts={"income": "200", "op": "200"})
        self.health["minimum_exempt"] = True
        self.assertEqual(self.row()["minimum_opt_out"], 1)

    def test_other_income_is_not_reported_as_op_eligible_income(self):
        self.records[0]["facts"]["op"] = "0"
        row = self.row(op_eligible=False)
        self.assertEqual(row["op_income"], 0)
        self.assertEqual(row["other_income"], 200)
        self.records[0]["facts"]["op"] = "1"
        with self.assertRaisesRegex(ValueError, "OP-ineligible"):
            self.row(op_eligible=False)

    def test_zero_month_does_not_invent_a_premium_assessed_worker(self):
        for record in self.records:
            record.update(base="0", amount="0")
        self.records[0]["facts"] = {"income": "0", "op": "0"}
        self.assertFalse(self.row(days=0)["premium_assessed"])

    def test_missing_side_profile_or_source_facts_require_review(self):
        for broken in (self.records[:1], self.records + self.records[:1]):
            with self.subTest(records=broken), self.assertRaises(ValueError):
                row_from_assessments(broken, self.health, op_eligible=True, days=30)
        self.health.pop("disabled")
        with self.assertRaisesRegex(ValueError, "complete recorded health profile"):
            self.row()

    def test_different_employer_base_does_not_invent_short_time_support(self):
        self.records[1]["base"] = "150"
        with self.assertRaisesRegex(ValueError, "legal reason"):
            self.row()
        self.records[1]["facts"]["shorttime_base"] = "150"
        self.assertEqual(self.row()["shorttime_base"], 150)
        self.records[1]["facts"]["shorttime_base"] = "149"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            self.row()

    def test_consolidation_unions_days_and_sums_actual_amounts_once(self):
        first, second = self.row(), self.row()
        first["_insured_dates"] = {"2026-06-01", "2026-06-02"}
        second["_insured_dates"] = {"2026-06-02", "2026-06-03"}
        merged = merge_assessment_rows([first, second])
        self.assertEqual(merged["days"], 3)
        self.assertEqual(merged["income"], 400)
        self.assertEqual(merged["total"], Decimal("67.46"))
        second["rate_employee"] = Decimal("2.5")
        with self.assertRaisesRegex(ValueError, "Inconsistent monthly"):
            merge_assessment_rows([first, second])
