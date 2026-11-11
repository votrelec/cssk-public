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

    def health_calendar(self, *extra, kind="2", start="2026-06-01", end="2026-06-30"):
        intervals = [(kind, start, end), *extra]
        result = (
            self.env["l10n.sk.health.calendar"]
            .with_company(self.company)
            .create(
                {
                    "employee_id": self.employee.id,
                    "company_id": self.company.id,
                    "month": "2026-06-01",
                    "complete": True,
                    "evidence": "Synthetic reviewed health calculation facts",
                    "interval_ids": [
                        Command.create(
                            {
                                "kind": code,
                                "date_start": lo,
                                "date_end": hi,
                            }
                        )
                        for code, lo, hi in intervals
                    ],
                }
            )
        )
        result.action_review()
        return result

    def test_calendar_benefits_leave_op_intact_but_reduce_minimum(self):
        self.version.l10n_sk_health_oop_claim = True
        self.health_calendar(("benefit", "2026-06-01", "2026-06-15"))
        slip = self.slip("none")
        self.assertEqual(
            self.health(slip),
            {
                "HEALTH": 0,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": -0.72,
            },
        )

    def test_no_income_days_reduce_op_and_minimum_independently(self):
        self.version.l10n_sk_health_oop_claim = True
        self.health_calendar(("2N", "2026-06-16", "2026-06-30"))
        slip = self.slip("none")
        self.assertEqual(
            self.health(slip),
            {
                "HEALTH": -5,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": 0,
            },
        )
        facts = {
            (row["fund"], row["side"]): row for row in slip._cssk_recorded_fund_bases()
        }
        self.assertEqual(float(facts[("health", "employee")]["base"]), 100)
        self.assertEqual(float(facts[("health", "employee")]["facts"]["op"]), 100)

    def test_last_day_disability_changes_both_rates_and_whole_month_minimum(self):
        calendar = self.health_calendar(("disabled", "2026-06-30", "2026-06-30"))
        slip = self.slip("none")
        self.assertFalse(self.version.l10n_sk_ztp)
        self.assertEqual(
            self.health(slip),
            {
                "HEALTH": -5,
                "HEALTHEMPLOYER": 11,
                "HEALTHDOPLATOK": 0,
            },
        )
        profile = slip.l10n_sk_fund_assessment["profile"]["health"]
        self.assertTrue(profile["disabled"])
        self.assertEqual(profile["calendar"]["calendar_id"], calendar.id)
        self.assertEqual(profile["calendar"]["minimum_days"], 0)

    def test_recognised_invalidity_conflict_is_readable_before_salary_rules(self):
        self.health_calendar()
        with self.assertRaisesRegex(UserError, "disability disagreement") as raised:
            self.slip("none", "disability")
        self.assertNotIn("Wrong python code", str(raised.exception))

    def test_concurrent_other_employer_disables_monthly_op_without_opt_out(self):
        self.version.l10n_sk_health_oop_claim = True
        self.health_calendar(("other_employment", "2026-06-30", "2026-06-30"))
        self.assertEqual(
            self.health(self.slip("none")),
            {
                "HEALTH": -10,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": -13.45,
            },
        )

    def test_self_employment_disables_op_and_reduces_minimum_by_actual_day(self):
        self.version.l10n_sk_health_oop_claim = True
        self.health_calendar(("self_employed", "2026-06-30", "2026-06-30"))
        self.assertEqual(
            self.health(self.slip("none")),
            {
                "HEALTH": -10,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": -11.93,
            },
        )

    def test_written_concurrent_opt_out_removes_only_the_minimum(self):
        self.version.write(
            {
                "l10n_sk_health_oop_claim": True,
                "l10n_sk_health_minimum_opt_out": True,
                "l10n_sk_health_minimum_evidence": "Synthetic written notice",
            }
        )
        self.health_calendar(("other_employment", "2026-06-30", "2026-06-30"))
        self.assertEqual(
            self.health(self.slip("none")),
            {
                "HEALTH": -10,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": 0,
            },
        )

    def test_opt_out_without_reviewed_concurrent_dates_is_rejected(self):
        self.version.write(
            {
                "l10n_sk_health_minimum_opt_out": True,
                "l10n_sk_health_minimum_evidence": "Synthetic written notice",
            }
        )
        with self.assertRaisesRegex(UserError, "proving concurrent employers"):
            self.slip("none")

    def test_partial_state_insured_days_do_not_exclude_actual_premiums(self):
        self.health_calendar(("state", "2026-06-16", "2026-06-30"))
        self.assertEqual(
            self.health(self.slip("none")),
            {
                "HEALTH": -10,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": 0,
            },
        )

    def test_op_rounds_up_after_calendar_proration_and_records_its_actual_base(self):
        self.version.l10n_sk_health_oop_claim = True
        self.health_calendar(start="2026-06-30")
        slip = self.slip("none")
        records = {
            (row["fund"], row["side"]): row for row in slip._cssk_recorded_fund_bases()
        }
        employee = records[("health", "employee")]
        self.assertAlmostEqual(float(employee["base"]), 193.33, places=6)
        self.assertAlmostEqual(float(employee["facts"]["op"]), 6.67, places=6)
        self.assertEqual(
            self.health(slip),
            {
                "HEALTH": -9.66,
                "HEALTHEMPLOYER": 22,
                "HEALTHDOPLATOK": 0,
            },
        )

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
