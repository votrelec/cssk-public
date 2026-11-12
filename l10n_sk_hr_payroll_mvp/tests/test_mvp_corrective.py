# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""An electronic correction replaces the complete filed monthly statement."""

import base64
from datetime import date
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import new_test_user
from odoo.addons.l10n_cssk_payroll_declaration_base.tests.common import confirm_payslips
from odoo.tools import file_path

from .test_mvp import NS, MvpCase


class TestMvpCorrective(MvpCase):
    def test_forged_period_projection_is_rejected_before_export(self):
        self._employee_payslip()
        original = self._report()
        original.action_generate()
        original.action_submit()
        corrective = self._report(
            month="4", correction_type="corrective", replaced_mvp_id=original.id
        )
        corrective.write({"date_from": date(2026, 3, 1), "date_to": date(2026, 3, 31)})
        with self.assertRaises(UserError):
            corrective.action_generate()
        self.assertFalse(corrective.xml_attachment_id)
        self.assertEqual(corrective.state, "draft")

    def test_explicit_context_false_preserves_unselected_predecessor(self):
        self._employee_payslip()
        original = self._report()
        original.action_generate()
        original.action_submit()
        model = self.env["l10n.sk.mvp"].with_context(default_replaced_mvp_id=False)
        corrective = model.create(
            {
                "company_id": self.company.id,
                "year": "2026",
                "month": "3",
                "correction_type": "corrective",
            }
        )
        self.assertFalse(corrective.replaced_mvp_id)
        with self.assertRaises(UserError):
            corrective.action_generate()
        corrective.replaced_mvp_id = original
        corrective.action_generate()
        for field in ("date_from", "date_to"):
            with self.assertRaises(UserError):
                corrective.write({field: date(2026, 4, 1)})

    def test_annual_projection_uses_native_annual_override(self):
        annual = self.env["l10n.sk.hlasenie"].new(
            {"company_id": self.company.id, "year": "2026", "month": "4"}
        )
        self.assertEqual(annual.date_from, date(2026, 1, 1))
        self.assertEqual(annual.date_to, date(2026, 12, 31))
        annual._check_period_projection()
        annual.date_to = date(2026, 4, 30)
        with self.assertRaises(UserError):
            annual._check_period_projection()

    def test_readonly_projection_cannot_disable_strict_correction_review(self):
        _employee, slip = self._employee_payslip()
        original = self._report()
        with patch.object(type(slip), "_cssk_recorded_fund_bases", return_value=False):
            original.action_generate()
            original.action_submit()
            corrective = self._report(correction_type="corrective")
            corrective.write({"is_correction": False})
            with self.assertRaises(UserError):
                corrective.action_generate()
            corrective.fund_bases_fallback_reason = (
                "Reviewed retained historical payroll."
            )
            corrective.action_confirm_legacy_fund_bases()
            corrective.action_generate()
            root = etree.fromstring(
                base64.b64decode(corrective.xml_attachment_id.datas)
            )
            self.assertEqual(root.find("m:typVykazu", NS).text, "O")

    def test_payroll_officer_generates_corrective_without_payroll_manager(self):
        officer = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="mvp-corrective-officer",
            groups="base.group_user,hr.group_hr_user,payroll.group_payroll_user",
            company_id=self.company.id,
            company_ids=[(6, 0, self.company.ids)],
        )
        # The OCA payroll-user role natively implies HR manager. Do not
        # misreport that standard role as an HR-only officer.
        self.assertFalse(officer.has_group("base.group_system"))
        self.assertFalse(officer.has_group("payroll.group_payroll_manager"))
        self._employee_payslip()
        model = self.env["l10n.sk.mvp"].with_user(officer).with_company(self.company)
        original = model.create(
            {"company_id": self.company.id, "year": "2026", "month": "3"}
        )
        original.action_generate()
        original.action_submit()
        corrective = model.create(
            {
                "company_id": self.company.id,
                "year": "2026",
                "month": "3",
                "correction_type": "corrective",
            }
        )
        corrective.action_generate()
        self.assertEqual(corrective.replaced_mvp_id, original)
        self.assertEqual(corrective.state, "generated")

    def _report(self, **values):
        return (
            self.env["l10n.sk.mvp"]
            .with_company(self.company)
            .create(
                {
                    "company_id": self.company.id,
                    "year": "2026",
                    "month": "3",
                    "payment_date": date(2026, 3, 31),
                    **values,
                }
            )
        )

    def test_corrective_is_available(self):
        self.assertIn("corrective", dict(self._report()._selection_correction_type()))

    def test_corrective_contains_all_current_employees_and_retains_original(self):
        self._employee_payslip()
        original = self._report()
        original.action_generate()
        original.action_submit()  # Local evidence only, no authority transport.
        archive = original.submitted_attachment_id
        old_bytes = base64.b64decode(archive.datas)
        self._employee_payslip(wage=1000, identification="8501021234")
        corrective = self._report(correction_type="corrective")
        self.assertEqual(corrective.replaced_mvp_id, original)
        corrective.action_generate()
        root = etree.fromstring(base64.b64decode(corrective.xml_attachment_id.datas))
        self.assertEqual(root.find("m:typVykazu", NS).text, "O")
        self.assertEqual(len(root.findall(".//m:poistneZamestnanca", NS)), 2)
        schema = etree.XMLSchema(
            etree.parse(file_path("l10n_sk_hr_payroll_mvp/data/MVPP-v2026.xsd"))
        )
        schema.assertValid(root)
        self.assertEqual(base64.b64decode(archive.datas), old_bytes)
        self.assertIn(archive, original.filed_history_ids)
        self.assertEqual(original.state, "submitted")
        with self.assertRaises(UserError):
            corrective.write({"replaced_mvp_id": False})

    def test_corrective_needs_retained_exact_filing(self):
        _employee, slip = self._employee_payslip()
        original = self._report()
        original.action_generate()
        corrective = self._report(
            correction_type="corrective", replaced_mvp_id=original.id
        )
        with self.assertRaises(UserError):
            corrective.action_generate()
        original.action_submit()
        april = slip.copy({"date_from": date(2026, 4, 1), "date_to": date(2026, 4, 30)})
        april.compute_sheet()
        confirm_payslips(april)
        other_period = self._report(month="4")
        other_period.action_generate()
        other_period.action_submit()
        corrective.replaced_mvp_id = other_period
        with self.assertRaises(UserError):
            corrective.action_generate()

    def test_regular_cannot_replace_and_copy_clears_reference(self):
        self._employee_payslip()
        original = self._report()
        original.action_generate()
        original.action_submit()
        corrective = self._report(correction_type="corrective")
        copied = corrective.copy()
        self.assertFalse(copied.replaced_mvp_id)
        regular = self._report(replaced_mvp_id=original.id)
        with self.assertRaises(UserError):
            regular.action_generate()

    def test_ambiguous_prior_requires_explicit_selection(self):
        self._employee_payslip()
        first, second = self._report(), self._report()
        for report in first | second:
            report.action_generate()
            report.action_submit()
        corrective = self._report(correction_type="corrective")
        self.assertFalse(corrective.replaced_mvp_id)
        with self.assertRaises(UserError):
            corrective.action_generate()
        corrective.replaced_mvp_id = second
        corrective.action_generate()

    def test_2027_full_fund_totals_are_not_a_difference(self):
        period = date(2027, 3, 1), date(2027, 3, 31)
        self._employee_payslip(period=period)
        original = self._report(year="2027", payment_date=date(2027, 3, 31))
        original.action_generate()
        original.action_submit()
        self._employee_payslip(wage=1000, identification="8501021234", period=period)
        corrective = self._report(
            year="2027", payment_date=date(2027, 3, 31), correction_type="corrective"
        )
        corrective.action_generate()
        root = etree.fromstring(base64.b64decode(corrective.xml_attachment_id.datas))
        self.assertEqual(root.find("m:obdobie", NS).text, "032027")
        self.assertEqual(root.find("m:typVykazu", NS).text, "O")
        # All3000 EUR of current income, not just the additional1000 EUR.
        self.assertEqual(root.find("m:poistne/m:np/m:npZamnec", NS).text, "42.00")
        self.assertEqual(root.find("m:poistne/m:sp/m:spZamnec", NS).text, "120.00")
        self.assertEqual(len(root.findall(".//m:poistneZamestnanca", NS)), 2)
