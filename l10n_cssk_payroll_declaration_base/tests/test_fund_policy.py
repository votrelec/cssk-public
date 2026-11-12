# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The optional reader protocol must not require a payroll engine."""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFundPolicyWithoutRecorder(TransactionCase):
    def test_virtual_original_retains_warning_without_chatter(self):
        source = self.env["hr.employee"].create({"name": "Synthetic missing fund source"})
        report = self.env["cssk.payroll.declaration.mixin"].new({
            "company_id": source.company_id.id, "year": "2026", "month": "6"})
        self.assertFalse(report.id)
        # Simulate the documented optional bridge protocol on a real HR
        # record; no engine, monetary source or country export is invented.
        with patch.object(type(source), "_cssk_recorded_fund_bases", return_value=False, create=True):
            self.assertEqual(report._collect_payslip_fund_bases(source), {source.id: False})
            self.assertIn(source.name, report.fund_bases_warning)
            self.assertIn("Legacy gross-based fallback", report.fund_bases_warning)

    def test_virtual_unconfirmed_correction_still_rejects_missing_funds(self):
        source = self.env["hr.employee"].create({"name": "Synthetic missing corrective fund source"})
        report = self.env["cssk.payroll.declaration.mixin"].new({
            "company_id": source.company_id.id, "year": "2026", "month": "6",
            "correction_type": "corrective"})
        with patch.object(type(source), "_cssk_recorded_fund_bases", return_value=False, create=True):
            with self.assertRaises(UserError):
                report._collect_payslip_fund_bases(source)

    def test_original_and_correction_without_a_reader_keep_existing_behaviour(self):
        # A real HR record supplies the minimal id/company/access protocol
        # without installing either payroll engine or inventing its model.
        # Native VPP integration tests cover actual engine implementations.
        source = self.env["hr.employee"].create({"name": "Synthetic no-reader source"})
        self.assertFalse(callable(getattr(source, "_cssk_recorded_fund_bases", None)))
        for correction in (False, True):
            with self.subTest(correction=correction):
                report = self.env["cssk.payroll.declaration.mixin"].new(
                    {
                        "company_id": source.company_id.id,
                        "year": "2026",
                        "month": "6",
                        "fund_bases_warning": False,
                    }
                )
                report.is_correction = correction
                records, missing = report._payslip_fund_records(source)
                self.assertEqual(records, {source.id: False})
                self.assertFalse(missing)
                self.assertEqual(
                    report._collect_payslip_fund_bases(source), {source.id: False}
                )
                self.assertFalse(report.fund_bases_warning)
