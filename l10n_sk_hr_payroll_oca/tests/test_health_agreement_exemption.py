# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Statutory health-income exclusions versus ordinary pensioner employment."""

from odoo import Command
from odoo.addons.l10n_sk_hr_payroll_base.applicability import PENSION_TYPES
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHealthAgreementExemption(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.company = cls.env["res.company"].create(
            {
                "name": "Synthetic statutory health exclusions",
                "country_id": cls.env.ref("base.sk").id,
            }
        )
        cls.env.user.company_ids |= cls.company
        calendar = cls.env["resource.calendar"].create(
            {
                "name": "Synthetic two-hour weekly work schedule",
                "company_id": cls.company.id,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Monday work",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 10,
                            "day_period": "morning",
                        }
                    )
                ],
            }
        )
        cls.employee = (
            cls.env["hr.employee"]
            .with_company(cls.company)
            .create(
                {
                    "name": "Synthetic low-hours health employee",
                    "company_id": cls.company.id,
                    "date_version": "2026-01-01",
                    "contract_date_start": "2026-01-01",
                    "wage": 200,
                    "resource_calendar_id": calendar.id,
                    "struct_id": cls.env.ref(
                        "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary"
                    ).id,
                    "l10n_sk_health_exempt": False,
                    "l10n_sk_health_oop_claim": False,
                }
            )
        )
        cls.version = cls.employee.version_id

    def slip(self, form, pension=False):
        xmlid = (
            "hr_payroll_structure_sk_employee_salary"
            if form == "none"
            else "hr_payroll_structure_sk_" + form
        )
        self.version.write(
            {
                "struct_id": self.env.ref("l10n_sk_hr_payroll_oca." + xmlid).id,
                "l10n_sk_pension_type": pension,
            }
        )
        self.assertEqual(self.version.l10n_sk_employment_form(), form)
        result = (
            self.env["hr.payslip"]
            .with_company(self.company)
            .create(
                {
                    "name": "Synthetic actual health exclusion calculation",
                    "company_id": self.company.id,
                    "employee_id": self.employee.id,
                    "contract_id": self.version.id,
                    "struct_id": self.version.struct_id.id,
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                }
            )
        )
        result.compute_sheet()
        self.assertEqual(
            result.line_ids.filtered(lambda row: row.code == "GROSS").total, 200
        )
        return result

    def health(self, slip):
        return {
            code: sum(
                slip.line_ids.filtered(lambda row: row.code == code).mapped("total")
            )
            for code in ("HEALTH", "HEALTHEMPLOYER", "HEALTHDOPLATOK")
        }

    def assert_excluded(self, slip):
        self.assertEqual(
            self.health(slip), {"HEALTH": 0, "HEALTHEMPLOYER": 0, "HEALTHDOPLATOK": 0}
        )
        records = {
            (row["fund"], row["side"]): row for row in slip._cssk_recorded_fund_bases()
        }
        for side in ("employee", "employer"):
            self.assertEqual(float(records[("health", side)]["base"]), 0)
            self.assertEqual(float(records[("health", side)]["amount"]), 0)

    def test_student_agreement_is_excluded_without_a_manual_exemption_checkbox(self):
        self.assert_excluded(self.slip("dobps"))

    def test_ordinary_employee_keeps_both_premiums_and_the_minimum_topup(self):
        self.assertEqual(
            self.health(self.slip("none")),
            {"HEALTH": -10, "HEALTHEMPLOYER": 22, "HEALTHDOPLATOK": -13.45},
        )

    def test_individual_exemption_needs_its_dated_basis_not_a_state_insuree_label(self):
        self.version.l10n_sk_health_exempt = True
        with self.assertRaisesRegex(UserError, "individual legal basis") as raised:
            self.slip("none", "old_age")
        self.assertTrue(
            str(raised.exception).startswith("Retain the individual legal basis")
        )
        self.assertNotIn("Wrong python code", str(raised.exception))
        self.employee.write(
            {
                "l10n_sk_health_exempt_evidence": "Synthetic reviewed applicable foreign coverage"
            }
        )
        self.employee.invalidate_recordset()
        self.assertTrue(self.version.l10n_sk_health_exempt_evidence)
        self.assert_excluded(self.slip("none", "old_age"))

    def test_both_pension_agreements_use_all_statutory_pension_profiles(self):
        # SERVICE_AT_AGE explicitly includes the reviewed retirement-age fact;
        # it does not mean any service pension regardless of age.
        for form in ("dovp", "dopc"):
            for pension in PENSION_TYPES:
                with self.subTest(form=form, pension=pension):
                    self.assert_excluded(self.slip(form, pension))

    def test_pensioner_employment_keeps_premiums_without_a_state_insuree_topup(self):
        # Section 12(2), footnote 48: recognised invalidity independently
        # establishes the reduced rate; a separate ZTP card is not required.
        invalidity = {
            "disability",
            "disability_over_70",
            "disability_at_age",
            "disability_service",
        }
        for pension in PENSION_TYPES:
            with self.subTest(pension=pension):
                employee, employer = (-5, 11) if pension in invalidity else (-10, 22)
                self.assertEqual(
                    self.health(self.slip("none", pension)),
                    {
                        "HEALTH": employee,
                        "HEALTHEMPLOYER": employer,
                        "HEALTHDOPLATOK": 0,
                    },
                )
