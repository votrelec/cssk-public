# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Actual two-remuneration health assessment versus one combined native oracle."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthlyHealthNative(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={**cls.env.context, "lang": "en_US"})
        values = {"name": "Synthetic monthly health", "country_id": cls.env.ref("base.sk").id}
        if "l10n_sk_health_insurer_code" in cls.env["res.company"]._fields:
            values.update(l10n_sk_health_insurer_code="24", l10n_sk_health_payer_number="9900112233")
        cls.company = cls.env["res.company"].create(values)
        cls.env.user.company_ids |= cls.company
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Synthetic health two hours weekly", "company_id": cls.company.id,
            "attendance_ids": [Command.create({
                "name": "Monday", "dayofweek": "0", "hour_from": 8,
                "hour_to": 10, "day_period": "morning",
            })],
        })
        cls.structure = cls.env.ref("l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary")

    def employee(self, wage=200, **extra):
        return self.env["hr.employee"].with_company(self.company).create({
            "name": "Synthetic monthly health employee", "company_id": self.company.id,
            "date_version": "2026-01-01", "contract_date_start": "2026-01-01",
            "wage": wage, "struct_id": self.structure.id,
            "resource_calendar_id": self.calendar.id, "l10n_sk_health_oop_claim": True,
            **extra,
        })

    def slip(self, employee, *, implicit=False, start=date(2026, 6, 1), end=date(2026, 6, 30)):
        slip = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Synthetic actual monthly remuneration", "company_id": self.company.id,
            "employee_id": employee.id, "struct_id": self.structure.id,
            "date_from": start, "date_to": end,
            **({} if implicit else {"contract_id": employee.version_id.id}),
        })
        slip.compute_sheet()
        slip.action_payslip_done()
        self.assertEqual(slip.state, "done")
        return slip

    def health(self, slips):
        return {
            code: sum(slips.mapped("line_ids").filtered(lambda line: line.code == code).mapped("total"))
            for code in ("HEALTH", "HEALTHEMPLOYER", "HEALTHDOPLATOK")
        }

    def test_two_200_remunerations_equal_combined_400_with_minimum_refund(self):
        employee = self.employee()
        first = self.slip(employee)
        frozen = deepcopy(first.l10n_sk_fund_assessment)
        old_ids = set(first.line_ids.ids)
        old_salary = sorted((line.id, line.code, line.amount, line.quantity, line.rate, line.total) for line in first.line_ids)
        self.assertEqual(self.health(first), {"HEALTH": 0, "HEALTHEMPLOYER": 22, "HEALTHDOPLATOK": -23.45})
        second = self.slip(employee)
        reference = self.slip(self.employee(400))
        self.assertEqual(self.health(reference), {"HEALTH": -3, "HEALTHEMPLOYER": 44, "HEALTHDOPLATOK": 0})
        self.assertEqual(set(first.line_ids.ids), old_ids)
        self.assertEqual(sorted((line.id, line.code, line.amount, line.quantity, line.rate, line.total)
                                for line in first.line_ids), old_salary)
        self.assertEqual(first.l10n_sk_fund_assessment, frozen)
        self.assertEqual(self.health(first | second), self.health(reference))
        self.assertEqual(self.health(second)["HEALTHDOPLATOK"], 23.45)
        self.assertAlmostEqual(
            sum((first | second).line_ids.filtered(lambda row: row.code == "TAXBASE").mapped("total")),
            sum(reference.line_ids.filtered(lambda row: row.code == "TAXBASE").mapped("total")),
            places=8,
        )

    def assert_split(self, wage, count=2, *, year=2026, implicit=False, **profile):
        employee = self.employee(wage, **profile)
        slips = self.env["hr.payslip"]
        for _index in range(count):
            slips |= self.slip(employee, implicit=implicit, start=date(year, 6, 1), end=date(year, 6, 30))
        reference = self.slip(self.employee(wage * count, **profile), start=date(year, 6, 1), end=date(year, 6, 30))
        for code, total in self.health(reference).items():
            self.assertAlmostEqual(self.health(slips)[code], total, places=8)
        self.assertFalse(any(slips.mapped("l10n_sk_monthly_fund_warning")))
        return slips, reference

    def test_two_250_negative_op_fragment(self):
        slips, _reference = self.assert_split(250)
        last = slips.sorted("id")[-1]
        ee = next(row for row in last.l10n_sk_fund_assessment["records"] if row["fund"] == "health" and row["side"] == "employee")
        self.assertEqual(float(ee["facts"]["op"]), -110)
        self.assertEqual(self.health(last)["HEALTHDOPLATOK"], 17.95)

    def test_three_remunerations_cross_op_threshold(self):
        self.assert_split(200, count=3)

    def test_implicit_native_contract(self):
        slips, _reference = self.assert_split(200, implicit=True)
        self.assertFalse(any(slips.mapped("contract_id")))

    def test_disabled(self):
        self.assert_split(200, l10n_sk_ztp=True)

    def test_2027_uses_dated_existing_parameter(self):
        slips, reference = self.assert_split(200, year=2027)
        self.assertEqual(self.health(slips.sorted("id")[0])["HEALTHDOPLATOK"], -25.23)
        self.assertEqual(self.health(reference)["HEALTHDOPLATOK"], -0.23)

    def reviewed(self, employee, kind):
        calendar = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
            "company_id": self.company.id, "employee_id": employee.id,
            "month": "2026-06-01", "complete": True,
            "evidence": "Synthetic reviewed monthly health source",
            "interval_ids": [Command.create({"kind": code, "date_start": start, "date_end": end})
                             for code, start, end in [("2", "2026-06-01", "2026-06-30"),
                                                     (kind, "2026-06-01", "2026-06-20")]],
        })
        calendar.action_review()

    def check_calendar_split(self, kind):
        employee, reference_employee = self.employee(), self.employee(400)
        for person in (employee, reference_employee):
            self.reviewed(person, kind)
        first, second = self.slip(employee), self.slip(employee)
        reference = self.slip(reference_employee)
        self.assertEqual(self.health(first | second), self.health(reference))
        self.assertFalse((first | second).mapped("l10n_sk_monthly_fund_warning")[0])

    def test_reviewed_benefit_days_count_once(self):
        self.check_calendar_split("benefit")

    def test_reviewed_2n_days_count_once(self):
        self.check_calendar_split("2N")

    def test_native_refund_latest_increment_and_replacement(self):
        employee = self.employee()
        first, second = self.slip(employee), self.slip(employee)
        frozen = deepcopy(first.l10n_sk_fund_assessment)
        original_salary = sorted((row.code, row.amount, row.quantity, row.rate, row.total) for row in second.line_ids)
        second.refund_sheet()
        refund = second.refunded_id
        self.assertTrue(refund)
        self.assertEqual(sorted((row.code, row.amount, row.quantity, row.rate, row.total) for row in refund.line_ids), original_salary)
        replacement = self.slip(employee)
        reference = self.slip(self.employee(400))
        self.assertEqual(self.health(first | replacement), self.health(reference))
        self.assertEqual(first.l10n_sk_fund_assessment, frozen)

    def test_custom_native_amount_and_matching_metadata_are_preserved(self):
        employee = self.employee()
        self.slip(employee)
        rule = self.structure.rule_ids.filtered(lambda row: row.code == "HEALTH")
        rule.amount_python_compute += (
            "\nresult -= 1\n"
            "if payslip._l10n_sk_is_recording_funds():\n"
            "    l10n_sk_fund_record['amount'] = str(-result)\n"
        )
        custom = self.slip(employee)
        self.assertEqual(self.health(custom), {
            "HEALTH": -1, "HEALTHEMPLOYER": 22, "HEALTHDOPLATOK": -22.45,
        })
        self.assertTrue(custom.l10n_sk_monthly_fund_warning)

    def test_peer_reader_access_error_propagates(self):
        employee = self.employee()
        first = self.slip(employee)
        current = first.copy()
        source = next(row for row in first.l10n_sk_fund_assessment["records"]
                      if row["fund"] == "health")["facts"]["monthly_health"]
        with patch.object(type(first), "_cssk_recorded_fund_bases", side_effect=AccessError("Synthetic denied source")):
            with self.assertRaisesRegex(AccessError, "Synthetic denied source"):
                current._monthly_health_sources(source["policy"])
