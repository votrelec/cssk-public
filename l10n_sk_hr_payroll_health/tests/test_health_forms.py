# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The company's default insurer and payer number decide what the health
filings carry, so they must be editable on the company form."""

from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHealthForms(TransactionCase):
    def _form_fields(self, model):
        arch = self.env[model].get_views([(False, "form")])[
            "views"]["form"]["arch"]
        return {n.get("name") for n in etree.fromstring(arch).iter("field")}

    def test_company_form_carries_health_defaults(self):
        names = self._form_fields("res.company")
        self.assertIn("l10n_sk_health_insurer_code", names)
        self.assertIn("l10n_sk_health_payer_number", names)

    def test_employee_form_carries_insurer(self):
        self.assertIn("l10n_sk_health_insurer_code",
                      self._form_fields("hr.employee"))

    def test_changing_default_insurer_preserves_each_assigned_payer_number(self):
        company = self.env["res.company"].create({
            "name": "Synthetic payer settings", "l10n_sk_health_insurer_code": "24",
            "l10n_sk_health_payer_number": "1111111111",
        })
        company.l10n_sk_health_payer_vszp = "2222222222"
        self.assertEqual(company.l10n_sk_health_payer_number, "1111111111")
        company.l10n_sk_health_insurer_code = "25"
        self.assertEqual(company.l10n_sk_health_payer_number, "2222222222")
        self.assertEqual(company._l10n_sk_health_payer_for_insurer("24"), "1111111111")
        company.l10n_sk_health_payer_number = "3333333333"
        self.assertEqual(company.l10n_sk_health_payer_vszp, "3333333333")
        self.assertEqual(company.l10n_sk_health_payer_dovera, "1111111111")

    def test_conflicting_default_and_insurer_specific_inputs_are_not_silently_prioritised(self):
        company = self.env["res.company"].create({
            "name": "Synthetic conflicting payer", "l10n_sk_health_insurer_code": "24",
            "l10n_sk_health_payer_number": "1111111111",
        })
        with self.assertRaises(ValidationError):
            company.write({
                "l10n_sk_health_payer_number": "2222222222",
                "l10n_sk_health_payer_dovera": "3333333333",
            })
        self.assertEqual(company.l10n_sk_health_payer_number, "1111111111")

    def test_legacy_company_setting_is_migrated_only_to_its_known_insurer(self):
        company = self.env["res.company"].create({
            "name": "Synthetic old payer", "l10n_sk_health_insurer_code": "24",
            "l10n_sk_health_payer_number": "1111111111",
        })
        self.env.cr.execute(
            "UPDATE res_company SET l10n_sk_health_payer_dovera = NULL WHERE id = %s", [company.id],
        )
        company.invalidate_recordset(["l10n_sk_health_payer_dovera"])
        self.env["res.company"]._l10n_sk_migrate_health_payer_settings()
        self.assertEqual(company.l10n_sk_health_payer_dovera, "1111111111")
        self.assertFalse(company.l10n_sk_health_payer_vszp)
        self.assertFalse(company.l10n_sk_health_payer_union)
