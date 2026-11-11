# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Signed capture, frozen native-formula parity and declaration policy."""

import ast
import json
from copy import deepcopy
from decimal import Decimal
from html import unescape
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from ..models.fund_capture import FundCapturePayslip


@tagged("post_install", "-at_install")
class TestRecordedFundPayroll(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.company = cls.env["res.company"].create(
            {
                "name": "Fund parity company",
                "country_id": cls.env.ref("base.sk").id,
            }
        )
        cls.env.user.company_ids |= cls.company
        cls.structure = cls.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary"
        )
        # Isolate reference arithmetic from the optional minimum-wage rule.
        # That rule has its own statutory tests; these cases deliberately use
        # small/sub-cent inputs and must not silently become a 915 EUR wage.
        cls.structure.rule_ids -= cls.structure.rule_ids.filtered(
            lambda rule: rule.code == "MIN_WAGE_TOPUP"
        )
        cls.adjustment = cls.env["hr.salary.rule"].create(
            {
                "name": "Synthetic signed gross adjustment",
                "code": "FUND_ADJUSTMENT",
                "sequence": 90,
                "category_id": cls.env.ref("l10n_sk_hr_payroll_oca.ALW").id,
                "condition_select": "python",
                "condition_python": "result = 'FUND_ADJUSTMENT' in inputs.dict",
                "amount_select": "code",
                "amount_python_compute": "result = inputs.FUND_ADJUSTMENT.amount",
            }
        )
        cls.structure.rule_ids |= cls.adjustment
        cls.employee = (
            cls.env["hr.employee"]
            .with_company(cls.company)
            .create(
                {
                    "name": "Fund parity employee",
                    "company_id": cls.company.id,
                    "identification_id": "8501011234",
                    "date_version": "2024-01-01",
                    "contract_date_start": "2024-01-01",
                    "struct_id": cls.structure.id,
                    "wage": 500,
                    "l10n_sk_health_oop_claim": True,
                }
            )
        )
        cls.version = cls.employee.version_id

    def _slip(self, *, wage=500.123, clawback=0, credit_note=False, **values):
        rounded_wage = self.company.currency_id.round(wage)
        self.version.wage = rounded_wage
        adjustment = float(Decimal(str(wage)) - Decimal(str(rounded_wage))) + clawback
        inputs = (
            [
                Command.create(
                    {
                        "name": "Synthetic correction",
                        "code": "FUND_ADJUSTMENT",
                        "amount": adjustment,
                        "contract_id": self.version.id,
                    }
                )
            ]
            if adjustment
            else []
        )
        slip = (
            self.env["hr.payslip"]
            .with_company(self.company)
            .create(
                {
                    "name": "Native formula parity",
                    "employee_id": self.employee.id,
                    "company_id": self.company.id,
                    "contract_id": self.version.id,
                    "struct_id": self.version.struct_id.id,
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                    "credit_note": credit_note,
                    "input_line_ids": inputs,
                    **values,
                }
            )
        )
        slip.compute_sheet()
        return slip

    @staticmethod
    def _lines(slip):
        return sorted(
            (row.code, row.amount, row.quantity, row.rate, row.total)
            for row in slip.line_ids
        )

    def _funds(self, slip):
        return {
            (row["fund"], row["side"]): row
            for row in slip._cssk_recorded_fund_bases() or []
        }

    def _report(self, correction=False):
        if "cssk.payroll.declaration.mixin" not in self.env:
            self.skipTest("Shared declaration framework not installed")
        report = (
            self.env["cssk.payroll.declaration.mixin"]
            .with_company(self.company)
            .new(
                {
                    "company_id": self.company.id,
                    "year": "2026",
                    "month": "6",
                }
            )
        )
        report.is_correction = correction
        return report

    def _compare_reference_formulas(self, **values):
        observed = self._slip(**values)
        expected = self._lines(observed)
        native = json.loads(
            (Path(__file__).parent / "data/native_fund_rules.json").read_text()
        )
        rules = self.env["hr.salary.rule"].search(
            [
                ("code", "in", list(native)),
                ("id", "in", self.structure.rule_ids.ids),
            ]
        )
        saved = {rule.id: rule.amount_python_compute for rule in rules}
        try:
            for rule in rules:
                rule.amount_python_compute = unescape(native[rule.code])
            baseline = self._slip(**values)
            self.assertEqual(self._lines(baseline), expected)
            self.assertFalse(baseline.l10n_sk_fund_assessment)
        finally:
            for rule in rules:
                rule.amount_python_compute = saved[rule.id]
        return observed

    def test_arithmetic_matches_disclosed_reference_on_non_round_income(self):
        for wage in (0.06, 100.129, 379.995, 500.123, 569.999, 16764.015, 25000.129):
            with self.subTest(wage=wage):
                self.assertTrue(
                    self._compare_reference_formulas(wage=wage).l10n_sk_fund_assessment
                )

    def test_unaffected_native_formulas_keep_their_original_arithmetic(self):
        native = json.loads(
            (Path(__file__).parent / "data/native_fund_rules.json").read_text()
        )
        # This disclosed FIX changes health eligibility, not the other twelve
        # frozen formulas. The original JSON stays unchanged; independent
        # statutory profile tests cover the three deliberately changed rules.
        changed = {"HEALTH", "HEALTHEMPLOYER", "HEALTHDOPLATOK"}
        rules = self.structure.rule_ids.filtered(
            lambda rule: rule.code in native and rule.code not in changed
        )
        self.assertEqual(len(rules), 12)
        for rule in rules:
            original = ast.parse(unescape(native[rule.code]).strip())
            current = ast.parse(rule.amount_python_compute.strip())
            if rule.code != "HEALTHDOPLATOK":
                emission = current.body.pop()
                self.assertIsInstance(emission, ast.If)
                self.assertEqual(
                    ast.unparse(emission.test), "payslip._l10n_sk_is_recording_funds()"
                )
            self.assertEqual(ast.dump(current), ast.dump(original), rule.code)

    def test_negative_gross_and_computed_credit_note_keep_native_amounts(self):
        for credit in (False, True):
            with self.subTest(credit=credit):
                slip = self._compare_reference_formulas(
                    clawback=-1000.246, credit_note=credit
                )
                self.assertLess(
                    slip.line_ids.filtered(lambda row: row.code == "GROSS").total, 0
                )
                self.assertLess(
                    float(self._funds(slip)[("accident", "employer")]["base"]), 0
                )

    def test_subcent_input_reaches_actual_gross_without_rounding_away(self):
        slip = self._slip(wage=500.123)
        # Monetary line.total rounds for display; the rule category and the
        # uncapped accident assessment retain the actual sub-cent input.
        gross = float(self._funds(slip)[("accident", "employer")]["base"])
        self.assertAlmostEqual(gross, 500.123, places=6)
        self.assertNotEqual(gross, round(gross, 2))

    def test_non_round_premiums_pin_the_native_amounts(self):
        low = self._slip(wage=379.995)
        self.assertEqual(
            low.line_ids.filtered(lambda row: row.code == "HEALTHEMPLOYER").total, 41.79
        )
        edge = self._slip(wage=569.999)
        self.assertEqual(
            edge.line_ids.filtered(lambda row: row.code == "HEALTH").total, -28.49
        )

    def test_agreement_oop_is_applied_before_the_statutory_cap(self):
        self.version.struct_id = self.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dopc"
        )
        self.version.struct_id.rule_ids |= self.adjustment
        self.version.write(
            {
                "l10n_sk_agreement_oop": True,
                "l10n_sk_pension_type": "old_age",
                "l10n_sk_hourly_wage": 0,
            }
        )
        slip = self._slip(wage=0, clawback=17100)
        self.assertEqual(self._funds(slip)[("pension", "employee")]["base"], "16764")

    def _student_agreement(self, oop=True):
        self.version.struct_id = self.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dobps"
        )
        self.version.struct_id.rule_ids |= self.adjustment
        self.employee.write(
            {"birthday": "2005-01-01", "identification_id": "0501011234"}
        )
        self.version.write(
            {
                "l10n_sk_agreement_oop": oop,
                "l10n_sk_pension_type": False,
                "l10n_sk_hourly_wage": 20,
                "l10n_sk_health_exempt": True,
            }
        )

    def test_monthly_agreement_oop_is_not_reused_by_a_second_payment(self):
        self.version.struct_id = self.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dopc"
        )
        self.version.struct_id.rule_ids |= self.adjustment
        self.version.write({
            "l10n_sk_agreement_oop": True,
            "l10n_sk_pension_type": "old_age",
            "l10n_sk_hourly_wage": 0,
        })
        # Independent monthly reference before any source payment is posted.
        # The second payment is an extra gross remuneration, with no mutation
        # of the employment version or of the first confirmed salary lines.
        reference = self._slip(wage=0, clawback=400)
        expected = {line.code: line.total for line in reference.line_ids}
        first = self._slip(wage=0, clawback=200)
        first.action_payslip_done()
        before = self._lines(first)
        second = self._slip(wage=0, clawback=200)
        funds = self._funds(second)
        self.assertEqual(funds[("pension", "employee")]["base"], "200")
        self.assertEqual(funds[("pension", "employee")]["amount"], "8")
        for code in ("TAXBASE", "INCOMETAX", "NET"):
            with self.subTest(code=code):
                actual = sum(line.total for line in (first | second).line_ids
                             if line.code == code)
                self.assertAlmostEqual(actual, expected[code], places=2)
        self.assertEqual(self._lines(first), before)

    def test_monthly_adapter_does_not_overwrite_a_custom_charged_amount(self):
        self.version.struct_id = self.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dopc"
        )
        self.version.struct_id.rule_ids |= self.adjustment
        self.version.write({"l10n_sk_agreement_oop": True,
                            "l10n_sk_pension_type": "old_age", "l10n_sk_hourly_wage": 0})
        first = self._slip(wage=0, clawback=200)
        first.action_payslip_done()
        pension = self.version.struct_id.rule_ids.filtered(lambda rule: rule.code == "PENSION")
        pension.amount_python_compute += "\nresult -= 1\n"
        second = self._slip(wage=0, clawback=200)
        self.assertEqual(second.get_salary_line_total("PENSION"), -1)
        self.assertFalse(second.l10n_sk_fund_assessment)

    def test_monthly_scope_resolves_the_contract_for_api_created_payroll(self):
        self.version.struct_id = self.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dopc"
        )
        self.version.struct_id.rule_ids |= self.adjustment
        self.version.write({"l10n_sk_agreement_oop": True,
                            "l10n_sk_pension_type": "old_age", "l10n_sk_hourly_wage": 0})
        first = self._slip(wage=0, clawback=200)
        first.action_payslip_done()
        second = self._slip(wage=0, clawback=200, contract_id=False)
        self.assertFalse(second.contract_id)
        self.assertEqual(second._l10n_sk_version(), first.contract_id)
        self.assertEqual(self._funds(second)[("pension", "employee")]["amount"], "8")

    def test_unsupported_straddling_payroll_is_missing_not_silently_absent(self):
        prior = self._slip(wage=0, clawback=200,
                           date_from="2026-05-15", date_to="2026-06-14")
        prior.action_payslip_done()
        self.assertFalse(prior.l10n_sk_fund_assessment)
        current = self._slip(wage=0, clawback=200)
        self.assertTrue(current.l10n_sk_monthly_fund_warning)
        self.assertFalse(current._cssk_recorded_fund_bases())

    def test_unknown_monthly_metadata_keeps_native_calculation_with_warning(self):
        first = self._slip(wage=0, clawback=200)
        first.action_payslip_done()
        evidence = deepcopy(first.l10n_sk_fund_assessment)
        for row in evidence["records"]:
            if row["fund"] != "health":
                row["facts"]["monthly"] = True
        # Out-of-band old/custom metadata is not a caller capability and must
        # neither become exact evidence nor break the native computation.
        self.env.cr.execute(
            "UPDATE hr_payslip SET l10n_sk_fund_assessment = %s::jsonb WHERE id = %s",
            [json.dumps(evidence), first.id],
        )
        first.invalidate_recordset(["l10n_sk_fund_assessment"])
        second = self._slip(wage=0, clawback=200)
        self.assertTrue(second.line_ids)
        self.assertTrue(second.l10n_sk_monthly_fund_warning)
        self.assertFalse(second._cssk_recorded_fund_bases())

    def _split_regular_tax_case(self, *, children=0):
        self.version.write({"l10n_sk_tax_declaration_signed": True,
                            "l10n_sk_children_under_15": children})
        reference = self._slip(wage=0, clawback=1200)
        expected = {line.code: line.total for line in reference.line_ids}
        first = self._slip(wage=0, clawback=600)
        first.action_payslip_done()
        frozen = deepcopy(first.l10n_sk_fund_assessment), self._lines(first)
        second = self._slip(wage=0, clawback=600)
        return first, second, expected, frozen

    def test_monthly_tax_allowance_and_progressive_bands_are_used_once(self):
        first, second, expected, frozen = self._split_regular_tax_case()
        for code in ("TAXBASE", "INCOMETAX", "NET"):
            with self.subTest(code=code):
                observed = sum(line.total for line in (first | second).line_ids if line.code == code)
                self.assertAlmostEqual(observed, expected[code], places=2)
        self.assertEqual((first.l10n_sk_fund_assessment, self._lines(first)), frozen)

    def test_monthly_child_bonus_is_not_paid_twice(self):
        first, second, expected, frozen = self._split_regular_tax_case(children=1)
        for code in ("CHILD_BONUS", "INCOMETAX", "NET"):
            with self.subTest(code=code):
                observed = sum(line.total for line in (first | second).line_ids if line.code == code)
                self.assertAlmostEqual(observed, expected[code], places=2)
        self.assertEqual((first.l10n_sk_fund_assessment, self._lines(first)), frozen)

    def test_monthly_tax_progressive_bands_and_bonus_taper_three_payments(self):
        self.version.write({"l10n_sk_tax_declaration_signed": True,
                            "l10n_sk_children_under_15": 1})
        reference = self._slip(wage=0, clawback=12000)
        expected = {line.code: line.total for line in reference.line_ids}
        first = self._slip(wage=0, clawback=1200)
        first.action_payslip_done()
        frozen = deepcopy(first.l10n_sk_fund_assessment), self._lines(first)
        second = self._slip(wage=0, clawback=6000)
        second.action_payslip_done()
        third = self._slip(wage=0, clawback=4800)
        for code in ("TAXBASE", "CHILD_BONUS", "INCOMETAX", "NET"):
            with self.subTest(code=code):
                observed = sum(line.total for line in (first | second | third).line_ids if line.code == code)
                self.assertAlmostEqual(observed, expected[code], places=2)
        self.assertLess(second.line_ids.filtered(lambda line: line.code == "CHILD_BONUS").total, 0)
        self.assertEqual((first.l10n_sk_fund_assessment, self._lines(first)), frozen)

    def test_custom_tax_rule_keeps_native_amount_and_named_warning(self):
        first, second, unused, frozen = self._split_regular_tax_case()
        rule = self.structure.get_all_rules().filtered(lambda row: row.code == "INCOMETAX")
        rule.amount_python_compute += "\nresult = -42.0\n"
        second.compute_sheet()
        self.assertEqual(second.line_ids.filtered(lambda line: line.code == "INCOMETAX").total, -42)
        self.assertTrue(second.l10n_sk_monthly_tax_warning)
        self.assertFalse(second.l10n_sk_fund_assessment["profile"]["monthly_tax"]["complete"])
        self.assertEqual((first.l10n_sk_fund_assessment, self._lines(first)), frozen)

    def test_missing_monthly_tax_profile_preserves_native_with_warning(self):
        first, second, unused, frozen = self._split_regular_tax_case()
        evidence = deepcopy(first.l10n_sk_fund_assessment)
        evidence["profile"].pop("monthly_tax")
        self.env.cr.execute("UPDATE hr_payslip SET l10n_sk_fund_assessment=%s WHERE id=%s",
                            (json.dumps(evidence), first.id))
        first.invalidate_recordset(["l10n_sk_fund_assessment"])
        second.compute_sheet()
        self.assertTrue(second.l10n_sk_monthly_tax_warning)
        self.assertEqual(second.l10n_sk_fund_assessment["profile"]["monthly_tax"]["missing"], [first.id])

    def test_tax_rounds_each_progressive_band_mathematically(self):
        # FS section47 example has 6000.00 ->1328.63. Two extra cents expose
        # the difference between separately rounded bands and final-only round.
        self.version.l10n_sk_tax_declaration_signed = False
        slip = self._slip(wage=0, clawback=600)
        rule = self.structure.get_all_rules().filtered(lambda row: row.code == "INCOMETAX")
        result = rule._compute_rule({
            "payslip": slip, "contract": self.version, "employee": self.employee,
            "result_rules": SimpleNamespace(TAXBASE=SimpleNamespace(total=6000.02)),
        })
        self.assertEqual(self.company.currency_id.round(result["amount"]), -1328.64)

    def test_malformed_or_mismatched_monthly_tax_lines_are_missing_sources(self):
        first, second, unused, frozen = self._split_regular_tax_case()
        for lines in (True, {"TAXBASE": 0, "INCOMETAX": 0, "CHILD_BONUS": 0}):
            with self.subTest(lines=lines):
                evidence = deepcopy(frozen[0])
                evidence["profile"]["monthly_tax"]["lines"] = lines
                self.env.cr.execute("UPDATE hr_payslip SET l10n_sk_fund_assessment=%s WHERE id=%s",
                                    (json.dumps(evidence), first.id))
                first.invalidate_recordset(["l10n_sk_fund_assessment"])
                second.compute_sheet()
                self.assertTrue(second.l10n_sk_monthly_tax_warning)
                self.assertEqual(second.l10n_sk_fund_assessment["profile"]["monthly_tax"]["missing"], [first.id])

    def test_all_five_eligible_funds_reduce_income_before_the_cap(self):
        self._student_agreement()
        for income in (200, 16763.995, 16764, 16900, 17100):
            with self.subTest(income=income):
                funds = self._funds(self._slip(wage=0, clawback=income))
                expected = min(max(0, income - 200), 16764)
                for key in (
                    ("pension", "employee"),
                    ("disability", "employee"),
                    ("pension", "employer"),
                    ("disability", "employer"),
                    ("reserve", "employer"),
                ):
                    self.assertAlmostEqual(
                        float(funds[key]["base"]), expected, places=6
                    )
                self.assertEqual(float(funds[("accident", "employer")]["base"]), income)
                self.assertEqual(
                    float(funds[("guarantee", "employer")]["base"]), min(income, 16764)
                )

    def test_high_income_actual_pension_charges_use_full_cap_after_oop(self):
        self._student_agreement()
        funds = self._funds(self._slip(wage=0, clawback=17100))
        self.assertEqual(funds[("pension", "employee")]["amount"], "670.56")
        self.assertEqual(funds[("disability", "employee")]["amount"], "502.92")
        self.assertEqual(funds[("pension", "employer")]["amount"], "2346.96")
        self.assertEqual(funds[("disability", "employer")]["amount"], "502.92")
        self.assertEqual(funds[("reserve", "employer")]["amount"], "796.29")

    def test_without_oop_the_existing_maximum_still_applies(self):
        self._student_agreement(oop=False)
        funds = self._funds(self._slip(wage=0, clawback=17100))
        self.assertEqual(funds[("pension", "employee")]["base"], "16764")

    def test_year_boundary_uses_2026_and_2027_dated_oop_and_maximum(self):
        self._student_agreement()
        for start, end, oop, maximum in (
            ("2026-12-01", "2026-12-31", 200, 16764),
            ("2027-01-01", "2027-01-31", 300, 17820),
        ):
            with self.subTest(start=start):
                slip = self._slip(wage=0, clawback=19000, date_from=start, date_to=end)
                self.assertEqual(slip.rule_parameter("l10n_sk_dohoda_oop"), oop)
                self.assertEqual(
                    slip.rule_parameter("l10n_sk_monthly_taxable_max"), maximum
                )
                funds = self._funds(slip)
                self.assertEqual(float(funds[("pension", "employee")]["base"]), maximum)
                self.assertEqual(float(funds[("reserve", "employer")]["base"]), maximum)

    def test_positive_base_with_zero_rounded_premium_is_not_missing(self):
        row = self._funds(self._slip(wage=0.06))[("sickness", "employee")]
        self.assertEqual((row["base"], row["amount"]), ("0.06", "0"))

    def test_profile_is_stored_once_without_restricted_birth_number(self):
        evidence = self._slip().l10n_sk_fund_assessment
        serialized = json.dumps(evidence, sort_keys=True)
        self.assertIn("profile", evidence)
        self.assertNotIn(self.employee.identification_id, serialized)
        self.assertTrue(
            all(
                set(row["facts"])
                <= (
                    {"rule_code", "topup", "income", "op"}
                    if row["fund"] == "health"
                    else {"rule_code", "monthly", "monthly_unverified"}
                )
                for row in evidence["records"]
            )
        )
        self.assertLess(len(serialized.encode()), 8000)
        print("FUND_RECORD_JSON_BYTES=" + str(len(serialized.encode())))

    def test_rule_evaluation_cannot_rewrite_confirmed_evidence(self):
        slip = self._slip()
        slip.with_context(without_compute_sheet=True).action_payslip_done()
        before = deepcopy(slip.l10n_sk_fund_assessment)
        slip.get_lines_dict()
        slip._get_payslip_lines(slip.contract_id.ids, slip.id)
        for spoofed in (True, {"supported": slip.ids}):
            slip.with_context(_l10n_sk_fund_capture=spoofed).get_lines_dict()
        self.assertEqual(slip.l10n_sk_fund_assessment, before)

    def test_structure_without_country_records_emitted_funds(self):
        self.version.struct_id = self.structure.copy(
            {"name": "Custom structure", "country_id": False}
        )
        self.assertTrue(self._slip().l10n_sk_fund_assessment)

    def test_cross_month_calculates_and_stays_unrecorded(self):
        self.assertFalse(
            self._compare_reference_formulas(
                date_to="2026-07-31"
            ).l10n_sk_fund_assessment
        )

    def test_invalid_optional_metadata_does_not_block_native_payroll(self):
        rule = self.env.ref(
            "l10n_sk_hr_payroll_oca.l10n_sk_sickness_insurance_employee"
        )
        rule.amount_python_compute += '\nl10n_sk_fund_record = {"invalid": True}\n'
        slip = self._slip()
        self.assertTrue(slip.line_ids)
        self.assertFalse(slip.l10n_sk_fund_assessment)

    def test_custom_quantity_does_not_store_a_charge_different_from_native_line(self):
        rule = self.env.ref(
            "l10n_sk_hr_payroll_oca.l10n_sk_sickness_insurance_employee"
        )
        rule.amount_python_compute += "\nresult_qty = 2.0\n"
        slip = self._slip()
        self.assertTrue(slip.line_ids.filtered(lambda row: row.code == "SICK"))
        self.assertFalse(slip.l10n_sk_fund_assessment)

    def test_generated_field_and_context_default_cannot_be_supplied(self):
        slip = self._slip()
        with self.assertRaisesRegex(UserError, "generated"):
            slip.write({"l10n_sk_fund_assessment": False})
        with self.assertRaisesRegex(UserError, "generated"):
            slip.with_context(default_l10n_sk_fund_assessment={}).copy()

    def test_corrupt_source_warns_for_original_and_refuses_correction(self):
        slip = self._slip()
        slip.line_ids.filtered(lambda row: row.code == "HEALTH").amount = -17
        report = self._report()
        with patch.object(type(report), "message_post", create=True) as post:
            report._collect_payslip_fund_bases(slip)
            report._collect_payslip_fund_bases(slip)
            self.assertIn(slip.display_name, report.fund_bases_warning)
            self.assertEqual(post.call_count, 1)
        correction = self._report(correction=True)
        with self.assertRaisesRegex(UserError, "Precise recorded"):
            correction._collect_payslip_fund_bases(slip)

    def test_framework_policy_runs_during_totals_without_caller_flag(self):
        slip = self._slip()
        super(FundCapturePayslip, slip).write({"l10n_sk_fund_assessment": False})
        report = self._report()
        with (
            patch.object(type(report), "_report_code", "sk_mvp"),
            patch.object(type(report), "message_post", create=True),
        ):
            result = report._collect_payslip_totals(slip)
            self.assertIs(result["recorded_funds"][slip.id], False)
            self.assertIn(slip.display_name, report.fund_bases_warning)
        correction = self._report(correction=True)
        with (
            patch.object(type(correction), "_report_code", "sk_vpp"),
            self.assertRaisesRegex(UserError, "Precise recorded"),
        ):
            correction._collect_payslip_totals(slip)

    def test_missing_insurance_records_do_not_block_a_tax_report_correction(self):
        slip = self._slip()
        super(FundCapturePayslip, slip).write({"l10n_sk_fund_assessment": False})
        report = self._report(correction=True)
        with patch.object(type(report), "_report_code", "sk_monthly_tax_overview"):
            self.assertNotIn("recorded_funds", report._collect_payslip_totals(slip))

    def test_native_refund_adapter_and_pairing_are_owned_by_bridge(self):
        slip = self._slip()
        slip.with_context(without_compute_sheet=True).action_payslip_done()
        original = self._funds(slip)
        self.version.wage = 1500
        slip.refund_sheet()
        refund = slip.refunded_id
        self.assertTrue(refund.credit_note)
        for key, row in self._funds(refund).items():
            self.assertEqual(
                (row["base"], row["amount"]),
                (original[key]["base"], original[key]["amount"]),
            )
        self.assertFalse((slip | refund)._cssk_effective_fund_payslips())

    def test_profile_adapter_preserves_evidence_and_validates_its_identity(self):
        slip = self._slip()
        original = deepcopy(slip.l10n_sk_fund_assessment["profile"])
        profile = slip._cssk_recorded_fund_profile()
        self.assertEqual(profile, original)
        profile["health"]["disabled"] = not profile["health"]["disabled"]
        self.assertEqual(slip._cssk_recorded_fund_profile(), original)
        self.assertEqual(slip.l10n_sk_fund_assessment["profile"], original)
        slip.date_to = "2026-06-29"
        self.assertFalse(slip._cssk_recorded_fund_profile())

    def test_profile_access_failure_is_not_missing_evidence(self):
        slip = self._slip()
        with patch.object(
            type(slip),
            "_l10n_sk_checked_fund_profile",
            side_effect=AccessError("Synthetic denied read"),
        ):
            with self.assertRaises(AccessError):
                slip._cssk_recorded_fund_profile()

    def test_profile_reader_uses_the_native_refund_origin(self):
        slip = self._slip()
        slip.with_context(without_compute_sheet=True).action_payslip_done()
        profile = slip._cssk_recorded_fund_profile()
        self.version.l10n_sk_ztp = True
        slip.refund_sheet()
        self.assertEqual(slip.refunded_id._cssk_recorded_fund_profile(), profile)
