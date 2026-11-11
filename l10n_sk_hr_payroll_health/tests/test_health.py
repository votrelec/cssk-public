# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Runtime test — proves dávka 514 generation on BOTH payroll engines against
the official 514-2023.xsd element model (root MZSR). Because that published
schema is internally defective (single-char patterns, impossible integer
bounds) no instance can pass assertValid, so the pipeline runs it non-fatally;
the test asserts well-formedness + structural conformance (the three blocks,
NumberOfRecords = PersonData count, insurer code) and that the per-employee
health advances match the payslip. It also asserts the shipped XSD compiles."""
import base64
import json
from copy import deepcopy
import unittest
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError
from odoo.addons.l10n_cssk_payroll_declaration_base.tests.common import (
    confirm_payslips,
)
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_path


@tagged("post_install", "-at_install")
class TestHealth514(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.engine = cls._detect_engine()
        if not cls.engine:
            raise unittest.SkipTest(
                "no SK payroll engine installed "
                "(l10n_sk_hr_payroll_oca or l10n_sk_hr_payroll)")
        cls.company = cls.env["res.company"].create({
            "name": "SK Health Co s.r.o.",
            "country_id": cls.env.ref("base.sk").id,
            "company_registry": "12345679",
            "l10n_sk_dic": "1234567890",
            "l10n_sk_health_insurer_code": "24",
            "l10n_sk_health_payer_number": "9900112233",
        })
        cls.env.user.company_ids |= cls.company
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=cls.company.ids))
        if cls.engine == "oca":
            cls.env.user.group_ids |= cls.env.ref(
                "payroll.group_payroll_manager")
            cls.structure = cls.env.ref(
                "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary")
        else:
            cls.env.user.group_ids |= cls.env.ref(
                "hr_payroll.group_hr_payroll_manager")
            cls.structure = cls.env.ref(
                "l10n_sk_hr_payroll.hr_payroll_structure_sk_employee_salary")
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "SK 40h", "company_id": cls.company.id})
        cls.agreement_calendar = cls.env["resource.calendar"].create({
            "name": "Synthetic agreement two hours weekly", "company_id": cls.company.id,
            "attendance_ids": [Command.create({
                "name": "Monday", "dayofweek": "0", "hour_from": 8,
                "hour_to": 10, "day_period": "morning",
            })],
        })

    @classmethod
    def _detect_engine(cls):
        """Which SK payroll engine is installed, or None for neither.

        This used to test for the OCA engine and ASSUME the Enterprise one
        otherwise, then go on to ``env.ref`` an ``hr_payroll`` group. On a
        database with neither engine that raised in ``setUpClass``, so the whole
        suite errored instead of skipping -- and since a Community database
        without the OCA payroll engine is the common case, it had not run at
        all. That is how a fixture using a non-checksum-valid IČO survived
        unnoticed until 04da4a3.

        A missing engine is a skip, not a failure: there is no payslip to build
        a declaration from, and nothing in this module is under test without
        one.
        """
        if cls.env.ref(
                "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary",
                raise_if_not_found=False):
            return "oca"
        if cls.env.ref(
                "l10n_sk_hr_payroll.hr_payroll_structure_sk_employee_salary",
                raise_if_not_found=False):
            return "ee"
        return None

    def _employee_payslip(self, wage=2000.0, agreement="none", pension=False,
                         version_values=None, health_intervals=None, period_end=date(2026, 3, 31),
                         explicit_contract=False, additional_version_values=None):
        structure = self.structure
        if agreement != "none":
            module = "l10n_sk_hr_payroll_oca" if self.engine == "oca" else "l10n_sk_hr_payroll"
            structure = self.env.ref(module + ".hr_payroll_structure_sk_" + agreement)
        emp_vals = {
            "name": "Jozko Mrkvicka",
            "company_id": self.company.id,
            "resource_calendar_id": (self.calendar if agreement == "none" else self.agreement_calendar).id,
            "identification_id": "8501011234",
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "wage": wage,
        }
        if self.engine == "oca":
            emp_vals["struct_id"] = structure.id
        else:
            emp_vals["structure_type_id"] = structure.type_id.id
        employee = self.env["hr.employee"].with_company(
            self.company).create(emp_vals)
        if pension:
            employee.version_id.write({"l10n_sk_pension_type": pension,
                                       "l10n_sk_health_exempt": agreement != "none"})
        if version_values:
            employee.version_id.write(version_values)
        source_version = employee.version_id
        if additional_version_values:
            source_version.copy({"employee_id": employee.id, **additional_version_values})
        if health_intervals is not None:
            reviewed = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
                "company_id": self.company.id, "employee_id": employee.id,
                "month": "2026-03-01", "complete": True,
                "evidence": "Synthetic actual registered days",
                "interval_ids": [Command.create({"kind": kind, "date_start": start, "date_end": end})
                                 for kind, start, end in health_intervals],
            })
            reviewed.action_review()

        slip = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Payslip",
            "employee_id": employee.id,
            "struct_id": structure.id,
            "company_id": self.company.id,
            "date_from": date(2026, 3, 1),
            "date_to": period_end,
            **({"contract_id": source_version.id} if explicit_contract else {}),
        })
        if self.engine == "ee":
            slip = slip.with_context(salary_simulation=True)
        slip.compute_sheet()
        confirm_payslips(slip)
        return employee, slip

    def test_old_age_agreement_is_not_health_employment(self):
        for agreement in ("dopc", "dovp"):
            with self.subTest(agreement=agreement):
                _, slip = self._employee_payslip(200, agreement, "old_age")
                declaration = self.env["l10n.sk.health"].with_company(self.company).create({
                    "company_id": self.company.id, "year": "2026", "month": "3"})
                self.assertNotIn(slip, declaration._get_period_payslips())

    def test_old_age_employment_stays_in_health_report(self):
        _, slip = self._employee_payslip(2000, "none", "old_age")
        declaration = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        self.assertIn(slip, declaration._get_period_payslips())

    def test_all_statutory_pension_agreements_are_excluded(self):
        for pension in ("old_age", "early_old_age", "disability_over_70",
                        "disability", "disability_at_age", "service_at_age",
                        "disability_service"):
            for agreement in ("dopc", "dovp"):
                with self.subTest(pension=pension, agreement=agreement):
                    _, slip = self._employee_payslip(200, agreement, pension)
                    declaration = self.env["l10n.sk.health"].with_company(self.company).create({
                        "company_id": self.company.id, "year": "2026", "month": "3"})
                    self.assertNotIn(slip, declaration._get_period_payslips())
                    declaration._preflight()

    def test_statutory_pension_exclusion_does_not_require_a_second_checkbox(self):
        for pension, exempt in (("disability", False), ("old_age", False)):
            with self.subTest(pension=pension, exempt=exempt):
                _, slip = self._employee_payslip(200, "dopc", pension)
                self._version(slip).l10n_sk_health_exempt = exempt
                declaration = self.env["l10n.sk.health"].with_company(self.company).create({
                    "company_id": self.company.id, "year": "2026", "month": "3"})
                declaration._preflight()
                self.assertNotIn(slip, declaration._get_period_payslips())

    def test_foreign_insured_agreement_without_pension_is_excluded(self):
        for agreement in ("dopc", "dovp"):
            _, slip = self._employee_payslip(200, agreement)
            self._version(slip).write({
                "l10n_sk_health_exempt": True,
                "l10n_sk_health_exempt_evidence": "Synthetic reviewed foreign coverage",
            })
            slip.compute_sheet()
            slip.action_payslip_done()
            declaration = self.env["l10n.sk.health"].with_company(self.company).create({
                "company_id": self.company.id, "year": "2026", "month": "3"})
            declaration._preflight()
            self.assertNotIn(slip, declaration._get_period_payslips())
            self.assertEqual(slip.get_salary_line_total("HEALTH"), 0)
            self.assertEqual(slip.get_salary_line_total("HEALTHEMPLOYER"), 0)

    def test_mismatch_at_another_insurer_does_not_block_this_insurer(self):
        self.company.l10n_sk_health_payer_vszp = "8800112233"
        _, broken = self._employee_payslip(200, "dopc", "disability")
        broken.employee_id.l10n_sk_health_insurer_code = "25"
        self._version(broken).l10n_sk_health_exempt = False
        good_employee, good = self._employee_payslip()
        good_employee.l10n_sk_health_insurer_code = "24"
        declaration = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3", "insurer_code": "24"})
        declaration._preflight()
        self.assertIn(good, declaration._get_period_payslips())
        self.assertNotIn(broken, declaration._get_period_payslips())
        declaration.insurer_code = "25"
        declaration._preflight()

    def _version(self, slip):
        return self.env["l10n.sk.health"]._payslip_version(slip)

    def test_later_contract_cannot_add_old_age_agreement_to_health(self):
        employee, slip = self._employee_payslip(200, "dopc", "old_age")
        employee.create_version({"date_version": date(2026, 4, 1),
                                 "l10n_sk_pension_type": False,
                                 "l10n_sk_health_exempt": False})
        self.assertFalse(employee.version_id.l10n_sk_pension_type)
        self.assertEqual(self.env['l10n.sk.health']._payslip_version(slip).l10n_sk_pension_type, 'old_age')
        declaration = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        self.assertNotIn(slip, declaration._get_period_payslips())

    def _new_health_statement(self, insurer="24"):
        return self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3",
            "insurer_code": insurer,
        })

    def _generated_tree(self, statement):
        statement.action_generate()
        return etree.fromstring(base64.b64decode(statement.xml_attachment_id.datas))

    def test_recorded_op_base_rate_and_topup_reach_xml_separately(self):
        _employee, slip = self._employee_payslip(
            200, version_values={"l10n_sk_health_oop_claim": True},
        )
        statement = self._new_health_statement()
        root = self._generated_tree(statement)
        row = root.find("PersonData")
        self.assertEqual(row.findtext("BaseOfAssessOfEmployee"), "0.00")
        self.assertEqual(row.findtext("OP"), "200.00")
        self.assertEqual(row.findtext("TariffOfDeposit2"), "5.00")
        self.assertEqual(row.findtext("DepositOfEmployee"), "0.00")
        topup = -slip.get_salary_line_total("HEALTHDOPLATOK")
        self.assertGreater(topup, 0)
        self.assertAlmostEqual(float(row.findtext("DepositOffEmployeeAdd")), topup)
        self.assertAlmostEqual(float(root.findtext("InsuranceBody/DepositOfInsurance2")), topup)
        self.assertEqual(root.findtext("InsuranceBody/DepositOfInsurance3"), "0.00")
        self.assertFalse(statement.fund_bases_warning)

    @freeze_time("2026-04-15")
    def test_monthly_health_signed_fragments_equal_combined_xml_and_text(self):
        if self.engine != "oca":
            self.skipTest("The monthly health recorder is owned by the OCA engine")
        _employee, first = self._employee_payslip(
            200, version_values={"l10n_sk_health_oop_claim": True},
        )
        second = first.copy({"name": "Synthetic second remuneration"})
        second.compute_sheet()
        confirm_payslips(second)
        frozen = deepcopy(first.l10n_sk_fund_assessment)
        salary_ids = set(first.line_ids.ids)
        split = []
        for statement in (self._new_health_statement(), self._text_statement()):
            statement.action_generate()
            self.assertFalse(statement.fund_bases_warning)
            split.append(base64.b64decode(statement.xml_attachment_id.datas))
        company = self.company
        self.company = self.env["res.company"].create({
            "name": "Synthetic combined health reference", "country_id": company.country_id.id,
            "company_registry": company.company_registry, "l10n_sk_dic": company.l10n_sk_dic,
            "l10n_sk_health_insurer_code": "24", "l10n_sk_health_payer_number": "9900112233",
        })
        self.env.user.company_ids |= self.company
        self.calendar = self.calendar.copy({"company_id": self.company.id})
        self._employee_payslip(400, version_values={"l10n_sk_health_oop_claim": True})
        combined = []
        for statement in (self._new_health_statement(), self._text_statement()):
            statement.action_generate()
            self.assertFalse(statement.fund_bases_warning)
            combined.append(base64.b64decode(statement.xml_attachment_id.datas).replace(
                self.company.name.encode(), company.name.encode(),
            ))
        self.assertEqual(split, combined)
        self.assertEqual(first.l10n_sk_fund_assessment, frozen)
        self.assertEqual(set(first.line_ids.ids), salary_ids)

    def test_recorded_disability_group_is_not_inferred_from_a_rounded_rate(self):
        self._employee_payslip(2000, version_values={"l10n_sk_ztp": True})
        root = self._generated_tree(self._new_health_statement())
        self.assertEqual(root.findtext("InsuranceBody/NumberOfInsurancePersons1"), "0")
        self.assertEqual(root.findtext("InsuranceBody/NumberOfInsurancePersons2"), "1")
        self.assertEqual(root.findtext("InsuranceBody/DepositOfInsurance1"), "0.00")
        self.assertEqual(root.findtext("InsuranceBody/DepositOfInsurance3"), "110.00")
        self.assertEqual(root.findtext("InsuranceBody/DepositOfInsurance4"), "50.00")
        self.assertEqual(root.findtext("PersonData/NotAppliedMinimum"), "1")

    def test_nonzero_excluded_assessments_are_reviewed_before_filtering(self):
        _employee, slip = self._employee_payslip(200, "dopc")
        original = [(line.code, line.total) for line in slip.line_ids]
        statement = self._new_health_statement()
        profile = statement._health_payslip_profiles(slip)[slip.id]
        profile = dict(profile, exempt=True)
        # A deliberately inconsistent bridge response exercises the consumer
        # boundary without changing generated storage or historical payroll.
        with patch.object(type(statement), "_health_payslip_profiles", return_value={slip.id: profile}):
            with self.assertRaisesRegex(UserError, "nonzero health assessments"):
                statement._preflight()
        self.assertEqual([(line.code, line.total) for line in slip.line_ids], original)
        self.assertEqual(slip.state, "done")

    def test_future_insurer_change_does_not_redirect_historical_filing(self):
        employee, slip = self._employee_payslip()
        historical = self._version(slip)
        future = historical.copy({
            "employee_id": employee.id, "date_version": date(2027, 1, 1),
            "l10n_sk_health_insurer_code": "25",
        })
        self.assertEqual(employee.with_context(version_id=future.id).l10n_sk_health_insurer_code, "25")
        with freeze_time("2027-06-15"):
            employee._compute_current_version_id()
            employee.invalidate_recordset(["version_id"])
            self.assertEqual(employee.l10n_sk_health_insurer_code, "25")
            self.assertIn(slip, self._new_health_statement("24")._get_period_payslips())
            self.assertNotIn(slip, self._new_health_statement("25")._get_period_payslips())
            self._generated_tree(self._new_health_statement("24"))

    def test_shared_protocol_marks_partial_health_metadata_as_legacy(self):
        _employee, slip = self._employee_payslip()
        statement = self._new_health_statement()
        records, _missing = statement._payslip_fund_records(slip)
        partial = [row for row in records[slip.id] if row["fund"] != "health"]
        self.assertTrue(partial)
        original = slip.l10n_sk_fund_assessment
        with patch.object(type(slip), "_cssk_recorded_fund_bases", return_value=partial):
            result, missing = statement._payslip_fund_records(slip)
            self.assertFalse(result[slip.id])
            self.assertEqual(missing, slip)
            data = statement._collect_payslip_totals(slip)
            self.assertFalse(data["recorded_funds"][slip.id])
            self.assertTrue(statement.fund_bases_warning)
        self.assertEqual(slip.l10n_sk_fund_assessment, original)

    def test_noncallable_optional_profile_reader_preserves_legacy_protocol(self):
        _employee, slip = self._employee_payslip()
        with patch.object(type(slip), "_cssk_recorded_fund_profile", object()):
            self.assertFalse(self._new_health_statement()._payslip_fund_profiles(slip)[slip.id])

    def test_later_pension_card_edit_does_not_reinterpret_recorded_payroll(self):
        _employee, slip = self._employee_payslip(
            200, "dopc", health_intervals=[("2D", "2026-03-02", "2026-03-02")],
        )
        statement = self._new_health_statement()
        self._version(slip).l10n_sk_pension_type = "old_age"
        self.assertFalse(statement._health_payslip_profiles(slip)[slip.id]["exempt"])
        self.assertIn(slip, statement._get_period_payslips())
        statement._preflight()

    def test_fresh_insured_agreement_needs_actual_registered_days(self):
        self._employee_payslip(200, "dopc")
        with self.assertRaisesRegex(UserError, "Review actual agreement"):
            self._new_health_statement().action_generate()

    def test_recorded_agreement_uses_reviewed_days_without_requiring_a_second_checkbox(self):
        self._employee_payslip(
            200, "dopc", health_intervals=[("2D", "2026-03-02", "2026-03-02")],
        )
        root = self._generated_tree(self._new_health_statement())
        row = root.find("PersonData")
        self.assertEqual(row.findtext("NumberOfDays"), "1")
        self.assertEqual(row.findtext("ReceiptOfEmployee"), "0.00")
        self.assertEqual(row.findtext("TotalReceiptOfOther"), "200.00")

    def test_missing_recorded_profile_uses_framework_legacy_policy(self):
        _employee, slip = self._employee_payslip()
        statement = self._new_health_statement()
        with patch.object(type(slip), "_cssk_recorded_fund_profile", return_value=False):
            statement.action_generate()
            self.assertTrue(statement.fund_bases_warning)
            statement.action_submit()
            correction = statement.copy({"state": "draft", "correction_type": "corrective"})
            with self.assertRaisesRegex(UserError, "Precise recorded fund bases"):
                correction.action_generate()
            correction.fund_bases_fallback_reason = "Synthetic review of retained legacy payroll"
            correction.action_confirm_legacy_fund_bases()
            correction.action_generate()

    def test_malformed_profile_is_missing_evidence_instead_of_a_crash_or_silent_filter(self):
        _employee, slip = self._employee_payslip()
        statement = self._new_health_statement()
        profile = statement._payslip_fund_profiles(slip)[slip.id]
        variants = []
        broken = deepcopy(profile)
        broken["health"]["insurer_code"] = []
        variants.append(broken)
        broken = deepcopy(profile)
        broken["health"]["calendar"] = {
            "insured_days": 1, "insured_dates": ["2026-02-30"], "month_start": "2026-02-01",
        }
        variants.append(broken)
        broken = deepcopy(profile)
        broken["regular"] = "false"
        variants.append(broken)
        for broken in variants:
            with self.subTest(profile=broken):
                with patch.object(type(slip), "_cssk_recorded_fund_profile", return_value=broken):
                    records, missing = statement._payslip_fund_records(slip)
                    self.assertFalse(records[slip.id])
                    self.assertEqual(missing, slip)

    def _text_statement(self):
        self.env["res.partner.bank"].create({
            "partner_id": self.company.partner_id.id,
            "acc_number": "SK3112000000198742637541",
        })
        statement = self._new_health_statement()
        statement.export_format = "text514"
        return statement

    @freeze_time("2026-04-15")
    def test_text_file_uses_actual_payroll_and_exact_published_record_layout(self):
        self._employee_payslip()
        statement = self._text_statement()
        statement.action_generate()
        expected = (
            "N|514|12345679|9900112233|2400|20260415|1|1|1|1|\r\n"
            "202603|31|SK Health Co s.r.o.|12345679|9900112233|1234567890|||||||SK3112000000198742637541|\r\n"
            "1|11,00|5,00|||1|0|31|0|2000,00|0,00|2000,00|0,00|220,00|100,00|0,00|0,00|320,00|PO|1|\r\n"
            "1|8501011234|31|11,00|5,00|2000,00|2000,00|220,00|100,00|320,00|2000,00|0,00|0,00|0,00||0|0,00|\r\n"
        ).encode()
        self.assertEqual(base64.b64decode(statement.xml_attachment_id.datas), expected)
        self.assertEqual(statement.xml_attachment_id.name, "N5142603.001")
        self.assertEqual(statement.xml_attachment_id.mimetype, "text/plain")
        with self.assertRaisesRegex(UserError, "Reset the declaration"):
            statement.export_format = "xml"

    @freeze_time("2026-04-15")
    def test_text_correction_reuses_shared_workflow_and_retains_original_file(self):
        self._employee_payslip()
        original = self._text_statement()
        original.action_generate()
        original.action_submit()
        filed = original.submitted_attachment_id
        original_bytes = filed.datas
        correction = original.copy({"state": "draft", "correction_type": "corrective"})
        correction.action_generate()
        self.assertEqual(correction.xml_attachment_id.name, "O5142603.001")
        self.assertTrue(base64.b64decode(correction.xml_attachment_id.datas).startswith(b"O|514|"))
        correction.action_submit()
        self.assertEqual(original.submitted_attachment_id, filed)
        self.assertEqual(filed.datas, original_bytes)
        self.assertIn(filed, original.filed_history_ids)

    def test_text_counts_all_insurers_without_reporting_the_other_insurers_person(self):
        self._employee_payslip()
        other, _slip = self._employee_payslip(
            version_values={"l10n_sk_health_insurer_code": "25"},
        )
        other.identification_id = "9002022345"
        statement = self._text_statement()
        statement.action_generate()
        records = base64.b64decode(statement.xml_attachment_id.datas).decode().splitlines()
        summary = records[2].split("|")
        self.assertEqual(summary[0], "1")
        self.assertEqual(summary[19], "2")
        self.assertEqual(len(records), 4)
        self.assertNotIn("9002022345", records[3])

    def test_same_person_on_two_hr_records_is_consolidated_with_distinct_days(self):
        self._employee_payslip(2000)
        self._employee_payslip(1000)
        statement = self._text_statement()
        statement.action_generate()
        records = base64.b64decode(statement.xml_attachment_id.datas).decode().splitlines()
        self.assertEqual(len(records), 4)
        row = records[3].split("|")
        self.assertEqual(row[1:3], ["8501011234", "31"])
        self.assertEqual(row[5:10], ["3000,00", "3000,00", "330,00", "150,00", "480,00"])
        self.assertEqual(statement.lines_count, 2)

    def test_reviewed_zero_premium_calendar_cannot_hide_an_unprocessed_employee(self):
        self._employee_payslip()
        employee = self.env["hr.employee"].with_company(self.company).create({
            "name": "Synthetic whole-month benefit", "company_id": self.company.id,
            "date_version": "2026-01-01", "contract_date_start": "2026-01-01",
        })
        calendar = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
            "company_id": self.company.id, "employee_id": employee.id,
            "month": "2026-03-01", "complete": True,
            "evidence": "Synthetic full-month registered employment and benefit decision",
            "interval_ids": [Command.create({
                "kind": kind, "date_start": "2026-03-01", "date_end": "2026-03-31",
            }) for kind in ("2", "benefit")],
        })
        calendar.action_review()
        with self.assertRaisesRegex(UserError, "Complete payroll, including zero-premium"):
            self._text_statement().action_generate()

    def _unprocessed_employee(self, **values):
        return self.env["hr.employee"].with_company(self.company).create({
            "name": "Synthetic missing ordinary payroll", "company_id": self.company.id,
            "date_version": "2026-01-01", "contract_date_start": "2026-01-01",
            "identification_id": "9002022345", **values,
        })

    def test_missing_ordinary_employee_without_calendar_blocks_named(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        statement = self._text_statement()
        for export_format in ("xml", "text514"):
            with self.subTest(export_format=export_format), self.assertRaisesRegex(UserError, employee.name):
                statement.copy({"export_format": export_format}).action_generate()

    def test_partial_payroll_does_not_cover_an_unprocessed_second_contract(self):
        employee, _slip = self._employee_payslip(
            period_end=date(2026, 3, 15), version_values={"contract_date_end": "2026-03-15"},
        )
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-16",
            "contract_date_start": "2026-03-16", "contract_date_end": False,
        })
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_monthwide_slip_on_ended_contract_cannot_cover_a_new_contract(self):
        employee, _slip = self._employee_payslip(version_values={"contract_date_end": "2026-03-15"})
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-16",
            "contract_date_start": "2026-03-16", "contract_date_end": False,
        })
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_employee_calendar_cannot_cover_a_second_unprocessed_contract(self):
        if self.engine != "oca":
            self.skipTest("Explicit OCA source contract; Enterprise adapter is maintained separately")
        employee, _slip = self._employee_payslip(
            version_values={"contract_date_end": "2026-03-15"}, explicit_contract=True,
            additional_version_values={
                "date_version": "2026-03-16", "contract_date_start": "2026-03-16",
                "contract_date_end": False,
            },
            health_intervals=[("2", "2026-03-01", "2026-03-31")],
        )
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_contract_period_is_frozen_and_monthwide_ended_source_has_fifteen_days(self):
        employee, slip = self._employee_payslip(version_values={"contract_date_end": "2026-03-15"})
        profile = deepcopy(slip._cssk_recorded_fund_profile())
        self.assertEqual(profile["contract_period"], {"start": "2026-01-01", "end": "2026-03-15"})
        root = self._generated_tree(self._new_health_statement())
        self.assertEqual(root.findtext("PersonData/NumberOfDays"), "15")
        employee.version_id.contract_date_end = "2026-03-20"
        self.assertEqual(slip._cssk_recorded_fund_profile(), profile)

    def test_post_contract_2y_is_covered_by_actual_frozen_registration(self):
        if self.engine != "oca":
            self.skipTest("Explicit OCA contract binding; Enterprise maintainer mirrors the adapter")
        _employee, slip = self._employee_payslip(
            200, "dopc", version_values={"contract_date_end": "2026-03-15"},
            health_intervals=[("2Y", "2026-03-31", "2026-03-31")], explicit_contract=True,
        )
        self.assertEqual(slip._cssk_recorded_fund_profile()["health"]["calendar"]["irregular_dates"], ["2026-03-31"])
        statement = self._new_health_statement()
        root = self._generated_tree(statement)
        self.assertFalse(statement.fund_bases_warning)
        self.assertEqual(root.findtext("PersonData/NumberOfDays"), "1")
        self.assertEqual(root.findtext("PersonData/TotalReceiptOfOther"), "200.00")

    def test_full_month_benefit_keeps_registration_with_zero_premium_days(self):
        _employee, slip = self._employee_payslip(
            0, health_intervals=[(kind, "2026-03-01", "2026-03-31") for kind in ("2", "benefit")],
        )
        profile = slip._cssk_recorded_fund_profile()["health"]["calendar"]
        self.assertEqual((len(profile["employment_dates"]), profile["insured_days"]), (31, 0))
        statement = self._new_health_statement()
        self.assertEqual(self._generated_tree(statement).findtext("PersonData/NumberOfDays"), "0")
        self.assertEqual(statement._health_registered_counts(), (1, 1))

    def test_full_month_2n_remains_a_valid_zero_income_source(self):
        _employee, slip = self._employee_payslip(
            0, health_intervals=[("2N", "2026-03-01", "2026-03-31")],
        )
        profile = slip._cssk_recorded_fund_profile()["health"]["calendar"]
        self.assertEqual((profile["employment_dates"], profile["insured_days"]), ([], 0))
        self.assertEqual(slip.state, "done")

    def test_later_empty_calendar_does_not_reinterpret_a_retained_valid_profile(self):
        employee, slip = self._employee_payslip(
            health_intervals=[("2", "2026-03-01", "2026-03-31")],
        )
        original = self._new_health_statement()
        original.action_generate()
        original.action_submit()
        filed, profile = original.submitted_attachment_id.datas, deepcopy(slip._cssk_recorded_fund_profile())
        calendar = self.env["l10n.sk.health.calendar"].search([("employee_id", "=", employee.id)])
        revision = self.env["l10n.sk.health.calendar"].browse(calendar.action_create_revision()["res_id"])
        revision.interval_ids.unlink()
        revision.write({"complete": True, "evidence": "Synthetic later review, not a payroll rewrite"})
        revision.action_review()
        with self.assertRaisesRegex(UserError, employee.name):
            slip._l10n_sk_fund_profile()
        self.assertEqual(slip._cssk_recorded_fund_profile(), profile)
        original.copy({"state": "draft", "correction_type": "corrective"}).action_generate()
        self.assertEqual(original.submitted_attachment_id.datas, filed)

    def test_real_legacy_profile_without_contract_period_keeps_amounts_and_review_audit(self):
        _employee, slip = self._employee_payslip()
        evidence = deepcopy(slip.l10n_sk_fund_assessment)
        evidence["profile"].pop("contract_period")
        self.env.cr.execute(
            "UPDATE hr_payslip SET l10n_sk_fund_assessment = %s::jsonb WHERE id = %s",
            [json.dumps(evidence), slip.id],
        )
        slip.invalidate_recordset(["l10n_sk_fund_assessment"])
        original = self._new_health_statement()
        records, missing = original._payslip_fund_records(slip)
        self.assertTrue(records[slip.id])
        self.assertEqual(missing, slip)
        original.action_generate()
        self.assertIn(slip.display_name, original.fund_bases_warning)
        self.assertIn("contract coverage", original.fund_bases_warning)
        original.action_submit()
        filed = original.submitted_attachment_id.datas
        correction = original.copy({"state": "draft", "correction_type": "corrective"})
        with self.assertRaisesRegex(UserError, "Precise recorded fund bases"):
            correction.action_generate()
        correction.fund_bases_fallback_reason = "Synthetic review of retained contract and payroll dates"
        correction.action_confirm_legacy_fund_bases()
        digest, moment = correction.fund_bases_confirmation_digest, correction.fund_bases_confirmed_at
        correction.action_confirm_legacy_fund_bases()
        self.assertEqual((correction.fund_bases_confirmation_digest, correction.fund_bases_confirmed_at), (digest, moment))
        self.assertEqual(correction.fund_bases_confirmed_by, self.env.user)
        correction.action_generate()
        correction.action_reset_to_draft()
        evidence["profile"]["contract_period"] = {"start": "invalid", "end": None}
        self.env.cr.execute(
            "UPDATE hr_payslip SET l10n_sk_fund_assessment = %s::jsonb WHERE id = %s",
            [json.dumps(evidence), slip.id],
        )
        slip.invalidate_recordset(["l10n_sk_fund_assessment"])
        with self.assertRaisesRegex(UserError, "Precise recorded fund bases"):
            correction.action_generate()
        self.assertEqual(original.submitted_attachment_id.datas, filed)

    def test_partial_payroll_covers_an_ended_contract(self):
        self._employee_payslip(
            period_end=date(2026, 3, 15), version_values={"contract_date_end": "2026-03-15"},
        )
        self._text_statement().action_generate()

    def test_full_month_snapshot_still_covers_a_later_hr_version(self):
        employee, _slip = self._employee_payslip()
        employee.version_id.copy({"employee_id": employee.id, "date_version": "2026-03-16"})
        self._text_statement().action_generate()

    def test_two_confirmed_partial_payslips_cover_both_contracts(self):
        employee, _first = self._employee_payslip(
            period_end=date(2026, 3, 15), version_values={"contract_date_end": "2026-03-15"},
        )
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-16",
            "contract_date_start": "2026-03-16", "contract_date_end": False,
        })
        second = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Synthetic second contract payroll", "employee_id": employee.id,
            "company_id": self.company.id, "struct_id": self.structure.id,
            "date_from": "2026-03-16", "date_to": "2026-03-31",
        })
        if self.engine == "ee":
            second = second.with_context(salary_simulation=True)
        second.compute_sheet()
        confirm_payslips(second)
        self._text_statement().action_generate()

    def test_exempt_partial_payroll_cannot_hide_later_ordinary_employment(self):
        self._employee_payslip()
        employee, _slip = self._employee_payslip(
            200, "dopc", "old_age", period_end=date(2026, 3, 15),
            version_values={"contract_date_end": "2026-03-15"},
        )
        employee.name = "Synthetic partial exempt payroll"
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-16",
            "contract_date_start": "2026-03-16", "contract_date_end": False,
            "l10n_sk_agreement_type": "none", "l10n_sk_health_exempt": False,
            **({"struct_id": self.structure.id} if self.engine == "oca"
               else {"structure_type_id": self.structure.type_id.id}),
        })
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_missing_other_insurer_payroll_also_blocks_all_insurer_count(self):
        self._employee_payslip()
        employee = self._unprocessed_employee(l10n_sk_health_insurer_code="27")
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_hr_card_without_contract_start_does_not_invent_registration(self):
        self._employee_payslip()
        self._unprocessed_employee(contract_date_start=False)
        self._text_statement().action_generate()

    def test_empty_reviewed_calendar_cannot_hide_an_ordinary_contract(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        calendar = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
            "company_id": self.company.id, "employee_id": employee.id,
            "month": "2026-03-01", "complete": True, "evidence": "Synthetic empty month review",
        })
        calendar.action_review()
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_empty_reviewed_calendar_blocks_new_ordinary_payroll_by_name(self):
        with self.assertRaisesRegex(UserError, "Jozko Mrkvicka"):
            self._employee_payslip(health_intervals=[])

    def test_reviewed_full_month_2n_excludes_ordinary_registration(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        calendar = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
            "company_id": self.company.id, "employee_id": employee.id,
            "month": "2026-03-01", "complete": True, "evidence": "Synthetic no-income exclusion",
            "interval_ids": [Command.create({
                "kind": kind, "date_start": "2026-03-01", "date_end": "2026-03-31",
            }) for kind in ("2", "2N")],
        })
        calendar.action_review()
        self._text_statement().action_generate()

    def test_missing_archived_employee_is_checked_in_historical_month(self):
        self._employee_payslip()
        employee = self._unprocessed_employee(active=False, contract_date_end="2026-03-15")
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_ended_or_future_contract_does_not_require_march_payroll(self):
        self._employee_payslip()
        self._unprocessed_employee(contract_date_end="2026-02-28")
        self._unprocessed_employee(date_version="2026-04-01", contract_date_start="2026-04-01")
        self._text_statement().action_generate()

    def test_historical_ordinary_version_cannot_be_hidden_by_future_exemption(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-04-01",
            "l10n_sk_health_exempt": True,
            "l10n_sk_health_exempt_evidence": "Synthetic foreign coverage reference",
        })
        with self.assertRaisesRegex(UserError, employee.name):
            self._text_statement().action_generate()

    def test_future_ordinary_version_does_not_reinterpret_historical_exemption(self):
        self._employee_payslip()
        employee = self._unprocessed_employee(
            l10n_sk_health_exempt=True,
            l10n_sk_health_exempt_evidence="Synthetic foreign coverage reference",
        )
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-04-01",
            "l10n_sk_health_exempt": False,
        })
        self._text_statement().action_generate()

    def test_old_age_agreement_without_payroll_is_exempt_but_ordinary_is_not(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        employee.version_id.write({"l10n_sk_agreement_type": "dopc", "l10n_sk_pension_type": "old_age"})
        statement = self._text_statement()
        statement.action_generate()
        employee.version_id.l10n_sk_agreement_type = "none"
        with self.assertRaisesRegex(UserError, employee.name):
            statement.copy().action_generate()

    def test_agreement_without_registered_days_does_not_invent_payroll(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        employee.version_id.l10n_sk_agreement_type = "dopc"
        self._text_statement().action_generate()

    def test_actual_2d_and_post_contract_2y_require_payroll(self):
        self._employee_payslip()
        statement = self._text_statement()
        for kind in ("2D", "2Y"):
            with self.subTest(kind=kind), self.env.cr.savepoint():
                employee = self._unprocessed_employee(**(
                    {"contract_date_end": "2026-02-28"} if kind == "2Y" else {}
                ))
                employee.version_id.l10n_sk_agreement_type = "dopc"
                calendar = self.env["l10n.sk.health.calendar"].with_company(self.company).create({
                    "company_id": self.company.id, "employee_id": employee.id,
                    "month": "2026-03-01", "complete": True,
                    "evidence": "Synthetic actual registration evidence",
                    "interval_ids": [Command.create({
                        "kind": kind, "date_start": "2026-03-04", "date_end": "2026-03-04",
                    })],
                })
                calendar.action_review()
                with self.assertRaisesRegex(UserError, employee.name):
                    statement.copy().action_generate()
                # Keep the next subcase independent without changing reviewed facts.
                employee.version_id.write({
                    "l10n_sk_health_exempt": True,
                    "l10n_sk_health_exempt_evidence": "Synthetic foreign coverage reference",
                })

    def test_effective_exempt_version_supersedes_older_open_contract(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-01",
            "l10n_sk_health_exempt": True,
            "l10n_sk_health_exempt_evidence": "Synthetic foreign coverage reference",
        })
        self._text_statement().action_generate()

    def test_recorded_exempt_payroll_is_not_reinterpreted_by_later_hr_edits(self):
        self._employee_payslip()
        employee, _slip = self._employee_payslip(200, "dopc", "old_age")
        employee.version_id.write({
            "l10n_sk_agreement_type": "none", "l10n_sk_health_exempt": False,
            **({"struct_id": self.structure.id} if self.engine == "oca"
               else {"structure_type_id": self.structure.type_id.id}),
        })
        self._text_statement().action_generate()

    def test_historical_exempt_employee_with_draft_calendar_does_not_block(self):
        self._employee_payslip()
        employee = self._unprocessed_employee()
        employee.version_id.copy({
            "employee_id": employee.id, "date_version": "2026-03-01",
            "l10n_sk_health_exempt": True,
            "l10n_sk_health_exempt_evidence": "Synthetic foreign coverage reference",
        })
        self.env["l10n.sk.health.calendar"].with_company(self.company).create({
            "company_id": self.company.id, "employee_id": employee.id, "month": "2026-03-01",
        })
        self._text_statement().action_generate()

    def test_additional_export_cannot_repeat_unchanged_full_payroll(self):
        self._employee_payslip()
        original = self._text_statement()
        original.action_generate()
        original.action_submit()
        try:
            additional = original.copy({"state": "draft", "correction_type": "supplementary"})
            additional.action_generate()
        except UserError:
            # A UI which offers only the legally complete O replacement is
            # valid; it must not advertise a full-month A as a delta.
            return
        except ValueError as exc:
            if "correction_type" not in str(exc):
                raise
            return
        records = base64.b64decode(additional.xml_attachment_id.datas).decode().splitlines()
        total = sum(float(row.split("|")[9].replace(",", ".")) for row in records[3:])
        self.assertEqual(total, 0, "Unchanged payroll has zero additional premium, not the full month again")

    def test_each_insurer_keeps_its_own_payer_and_generated_inputs_are_stable(self):
        self.company.write({
            "l10n_sk_health_payer_dovera": "1111111111",
            "l10n_sk_health_payer_vszp": "2222222222",
        })
        self._insured("Synthetic payer24", "8501011234", "24")
        self._insured("Synthetic payer25", "9002022345", "25")
        first, second = self._new_health_statement("24"), self._new_health_statement("25")
        self.assertEqual(first.payer_number, "1111111111")
        self.assertEqual(second.payer_number, "2222222222")
        self.assertEqual(self._generated_tree(first).findtext("Identification/CodeOfPayer"), "1111111111")
        self.assertEqual(self._generated_tree(second).findtext("Identification/CodeOfPayer"), "2222222222")
        self.company.l10n_sk_health_payer_dovera = "3333333333"
        first.write({
            "company_id": self.company.id, "insurer_code": "24", "payer_number": "1111111111",
            "year": "2026", "month": "3", "payment_date": False,
        })
        self.assertEqual(first.payer_number, "1111111111")
        with self.assertRaisesRegex(UserError, "filing inputs"):
            first.payer_number = "3333333333"
        with self.assertRaisesRegex(UserError, "filing inputs"):
            first.insurer_code = "25"
        first.action_reset_to_draft()
        first.payer_number = "3333333333"
        self.assertEqual(first.payer_number, "3333333333")

    def test_explicit_statement_payer_is_allowed_without_changing_company_configuration(self):
        statement = self._new_health_statement("25")
        self.assertFalse(statement.payer_number)
        statement.payer_number = "5555555555"
        self.assertEqual(statement.payer_number, "5555555555")
        self.assertEqual(self.company.l10n_sk_health_payer_number, "9900112233")

    def test_payer_upgrade_reads_retained_bytes_instead_of_current_company_settings(self):
        self._employee_payslip()
        original = self._new_health_statement()
        original.action_generate()
        original.action_submit()
        filed = original.submitted_attachment_id.datas
        self.company.l10n_sk_health_payer_number = "6666666666"
        self.env.cr.execute("UPDATE l10n_sk_health SET payer_number = NULL WHERE id = %s", [original.id])
        original.invalidate_recordset(["payer_number"])
        self.env["l10n.sk.health"].with_context(bin_size=True)._l10n_sk_migrate_legacy_payer_numbers()
        self.assertEqual(original.payer_number, "9900112233")
        self.assertEqual(original.submitted_attachment_id.datas, filed)

    def test_generate_and_validate(self):
        employee, slip = self._employee_payslip()
        totals = {line.code: line.total for line in slip.line_ids}
        health_ee = abs(round(totals.get("HEALTH", 0.0), 2))
        health_er = abs(round(totals.get("HEALTHEMPLOYER", 0.0), 2))
        self.assertGreater(health_ee, 0.0, "employee health must be computed")
        self.assertGreater(health_er, 0.0, "employer health must be computed")

        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        })
        self.assertTrue(decl.version_id, "dávka 514 version should default")
        self.assertEqual(decl.insurer_code, "24", "insurer defaults from company")
        decl.action_generate()
        self.assertEqual(decl.state, "generated")

        xml_bytes = base64.b64decode(decl.xml_attachment_id.datas)
        root = etree.fromstring(xml_bytes)  # well-formed
        self.assertEqual(etree.QName(root).localname, "MZSR")

        # the shipped official XSD compiles (loads as an XMLSchema)
        etree.XMLSchema(etree.parse(
            file_path("l10n_sk_hr_payroll_health/data/514-2023.xsd")))

        # structural: the three header blocks present
        for block in ("Identification", "CorporateBody", "InsuranceBody"):
            self.assertIsNotNone(root.find(block), "missing %s" % block)

        # The DIČ must actually arrive. This element was emitted EMPTY for any
        # company without one -- _preflight checked the IČO, the payer number
        # and the insurer but not the DIČ, and the render context read it
        # through a getattr default, so the dávka went to the insurer with
        # nothing in it and raised nothing.
        self.assertEqual(
            root.findtext("CorporateBody/CompanyIDTaxCode")
            or root.findtext(".//CompanyIDTaxCode"),
            "1234567890",
            "the DIČ must reach <CompanyIDTaxCode>")

        # identification: 4-digit insurer code, IČO, NumberOfRecords
        self.assertEqual(
            root.findtext("Identification/CodeOfHealthInsuranceCompany"),
            "2400")
        self.assertEqual(root.findtext("Identification/IDCode"), "12345679")
        self.assertEqual(root.findtext("Identification/NumberOfRecords"), "1")
        self.assertEqual(root.findtext("CorporateBody/Period"), "2026-03")

        # one employee row, advances match the payslip
        rows = root.findall("PersonData")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0].findtext("IdentificationNumberOfInsured"), "8501011234")
        self.assertAlmostEqual(
            float(rows[0].findtext("DepositOfEmployee")), health_ee, 2)
        self.assertAlmostEqual(
            float(rows[0].findtext("DepositOfEmployer")), health_er, 2)

        # aggregate employer total matches the single row
        self.assertAlmostEqual(
            float(root.findtext("InsuranceBody/DepositOfInsurance1")),
            health_er, 2)

    def test_missing_payer_number_raises(self):
        self._employee_payslip()
        self.company.l10n_sk_health_payer_number = False
        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        with self.assertRaises(UserError):
            decl.action_generate()

    def test_generation_refuses_without_a_dic(self):
        """The silent failure this guards: no DIČ produced an empty
        <CompanyIDTaxCode> and no error. The Prehľad and the Hlásenie always
        refused in that situation; the dávka 514 did not."""
        self.company.l10n_sk_dic = False
        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        })
        with self.assertRaises(UserError):
            decl.action_generate()

    # ------------------------------------------------------------------
    # One insurer per dávka (2026-10-27)
    # ------------------------------------------------------------------
    def _insured(self, name, rc, insurer):
        employee, slip = self._employee_payslip(
            version_values={"l10n_sk_health_insurer_code": insurer},
        )
        employee.write({"name": name, "identification_id": rc,
                        "l10n_sk_health_insurer_code": insurer})
        return employee

    def _rows(self, insurer):
        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3",
            "insurer_code": insurer})
        decl.action_generate()
        root = etree.fromstring(base64.b64decode(decl.xml_attachment_id.datas))
        return decl, [p.findtext("IdentificationNumberOfInsured")
                      for p in root.findall("PersonData")]

    def test_each_insurer_gets_only_its_insurees(self):
        """Every employee went into every insurer's dávka 514: the insurer
        was a property of the record, never of the employee."""
        self.company.l10n_sk_health_payer_vszp = "8800112233"
        self._insured("Dovera Poistenec", "8501011234", "24")
        self._insured("Vszp Poistenec", "9002022345", "25")
        decl24, rows24 = self._rows("24")
        decl25, rows25 = self._rows("25")
        self.assertEqual(rows24, ["8501011234"])
        self.assertEqual(rows25, ["9002022345"])
        self.assertEqual(decl24.lines_count, 1)
        self.assertEqual(decl25.lines_count, 1)
        self.assertEqual(decl25.payer_number, "8800112233")

    def test_employee_initial_company_default_survives_later_company_change(self):
        employee, _slip = self._employee_payslip()
        self.assertEqual(employee.l10n_sk_health_insurer_code, "24")
        self.company.l10n_sk_health_payer_dovera = "9900112233"
        self.company.l10n_sk_health_insurer_code = "25"
        _decl, rows = self._rows("24")  # the company default
        self.assertEqual(rows, ["8501011234"])
        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3",
            "insurer_code": "25"})
        with self.assertRaises(UserError):
            decl.action_generate()  # nobody is insured with VšZP

    def test_company_fields_are_on_the_forms(self):
        """The payer number is required by the preflight but was on no form;
        the employee's insurer has to be visible to be set."""
        arch = self.env["l10n.sk.health"].get_views(
            [(False, "form")])["views"]["form"]["arch"]
        self.assertIn('name="payer_number"', arch)
        emp_arch = self.env["hr.employee"].get_views(
            [(False, "form")])["views"]["form"]["arch"]
        self.assertIn('name="l10n_sk_health_insurer_code"', emp_arch)
        decl = self.env["l10n.sk.health"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        decl.payer_number = "1122334455"
        self.assertEqual(decl.payer_number, "1122334455")
        self.assertEqual(self.company.l10n_sk_health_payer_number, "9900112233")

@tagged("post_install", "-at_install")
class TestSchemaPins(TransactionCase):
    """The bundled schemas must match data/SCHEMA_VERSION.

    Not a check that our copies are CURRENT — nothing local can answer that,
    and a schema revised in place by the authority validates exactly as
    before. What this checks is that the bundled bytes are the ones recorded
    in SCHEMA_VERSION, and that no schema sits in data/ unpinned.
    """

    @staticmethod
    def _data_dir():
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "data")

    def _pins(self):
        import os
        pins = {}
        path = os.path.join(self._data_dir(), "SCHEMA_VERSION")
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                parts = raw.split()
                if (len(parts) == 3 and parts[0].endswith(".xsd")
                        and "/" not in parts[0]):
                    pins[parts[0]] = (parts[1], int(parts[2]))
        return pins

    def test_bundled_schemas_match_the_pinned_digests(self):
        import hashlib
        import os
        pins = self._pins()
        self.assertTrue(pins, "SCHEMA_VERSION lists no schemas")
        for name, (digest, size) in pins.items():
            path = os.path.join(self._data_dir(), name)
            self.assertTrue(os.path.exists(path),
                            "%s is pinned but missing" % name)
            with open(path, "rb") as fh:
                blob = fh.read()
            self.assertEqual(len(blob), size, "%s size moved" % name)
            self.assertEqual(
                hashlib.md5(blob).hexdigest(), digest,
                "%s does not match its pin — if this is a deliberate "
                "refresh, update data/SCHEMA_VERSION" % name)

    def test_every_bundled_schema_is_pinned(self):
        import os
        on_disk = {f for f in os.listdir(self._data_dir())
                   if f.endswith(".xsd")}
        self.assertEqual(on_disk, set(self._pins()),
                         "unpinned schema(s): %s"
                         % sorted(on_disk - set(self._pins())))
