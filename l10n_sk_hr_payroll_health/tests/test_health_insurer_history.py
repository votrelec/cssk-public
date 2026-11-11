# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Insurer changes and an actual old employee column, on native HR versions."""

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestHealthInsurerHistory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Synthetic insurer history",
                "country_id": cls.env.ref("base.sk").id,
                "l10n_sk_health_insurer_code": "24",
            }
        )
        cls.hr_user = new_test_user(
            cls.env,
            login="synthetic_health_history_hr",
            groups="base.group_user,hr.group_hr_user",
            company_id=cls.company.id,
            company_ids=[Command.set(cls.company.ids)],
        )

    def employee(self, **extra):
        return self.env["hr.employee"].with_company(self.company).create(
            {
                "name": "Synthetic historical insuree",
                "company_id": self.company.id,
                "date_version": "2026-01-01",
                **extra,
            }
        )

    def legacy_value(self, employee, value):
        self.env.cr.execute(
            "ALTER TABLE hr_employee ADD COLUMN IF NOT EXISTS "
            "l10n_sk_health_insurer_code varchar"
        )
        self.env.cr.execute(
            "UPDATE hr_employee SET l10n_sk_health_insurer_code = %s WHERE id = %s",
            [value, employee.id],
        )

    @freeze_time("2026-06-15")
    def test_new_default_is_frozen_and_explicit_employee_value_is_delegated(self):
        employee = self.employee()
        self.assertEqual(employee.version_id.l10n_sk_health_insurer_code, "24")
        self.company.l10n_sk_health_insurer_code = "25"
        self.assertEqual(employee.l10n_sk_health_insurer_code, "24")
        explicit = self.employee(l10n_sk_health_insurer_code="27")
        self.assertEqual(explicit.version_id.l10n_sk_health_insurer_code, "27")
        explicit.l10n_sk_health_insurer_code = "25"
        self.assertEqual(explicit.version_id.l10n_sk_health_insurer_code, "25")
        self.assertFalse(employee._fields["l10n_sk_health_insurer_code"].store)

    @freeze_time("2026-06-15")
    def test_next_year_insurer_does_not_change_historical_profile(self):
        employee = self.employee()
        original = employee.version_id
        future = original.copy(
            {
                "employee_id": employee.id,
                "date_version": "2027-01-01",
                "l10n_sk_health_insurer_code": "27",
            }
        )
        self.assertEqual(original._l10n_sk_health_profile("2026-06-01")["insurer_code"], "24")
        self.assertEqual(future._l10n_sk_health_profile("2027-01-01")["insurer_code"], "27")
        self.assertEqual(employee.l10n_sk_health_insurer_code, "24")

    @freeze_time("2026-06-15")
    def test_migration_only_preserves_current_version_and_is_idempotent(self):
        employee = self.employee(l10n_sk_health_insurer_code=False)
        current = employee.version_id
        past = current.copy(
            {
                "employee_id": employee.id,
                "date_version": "2025-01-01",
                "l10n_sk_health_insurer_code": False,
            }
        )
        self.legacy_value(employee, "27")
        Version = self.env["hr.version"]
        self.assertEqual(Version._l10n_sk_migrate_legacy_insurers(), 1)
        self.assertEqual(current.l10n_sk_health_insurer_code, "27")
        self.assertFalse(past.l10n_sk_health_insurer_code)
        self.assertEqual(Version._l10n_sk_migrate_legacy_insurers(), 0)

    @freeze_time("2026-06-15")
    def test_migration_preserves_reviewed_value_and_ignores_invalid_legacy(self):
        reviewed = self.employee(l10n_sk_health_insurer_code="25")
        invalid = self.employee(l10n_sk_health_insurer_code=False)
        self.legacy_value(reviewed, "24")
        self.legacy_value(invalid, "99")
        self.assertEqual(self.env["hr.version"]._l10n_sk_migrate_legacy_insurers(), 0)
        self.assertEqual(reviewed.l10n_sk_health_insurer_code, "25")
        self.assertFalse(invalid.l10n_sk_health_insurer_code)

    @freeze_time("2026-06-15")
    def test_missing_historical_insurer_is_explicit_in_profile(self):
        employee = self.employee(l10n_sk_health_insurer_code=False)
        profile = employee.version_id._l10n_sk_health_profile("2026-06-01")
        self.assertIsNone(profile["insurer_code"])
        self.assertIn("calendar", profile)
        self.assertIn("exempt", profile)

    @freeze_time("2026-06-15")
    def test_native_history_action_edits_only_selected_version_as_hr_user(self):
        employee = self.employee()
        original = employee.version_id
        future = original.copy(
            {
                "employee_id": employee.id,
                "date_version": "2027-01-01",
                "l10n_sk_health_insurer_code": "27",
            }
        )
        action = future.with_user(self.hr_user).action_open_version()
        selected = employee.with_user(self.hr_user).with_context(**action["context"])
        self.assertEqual(selected.l10n_sk_health_insurer_code, "27")
        selected.l10n_sk_health_insurer_code = "25"
        self.assertEqual(future.l10n_sk_health_insurer_code, "25")
        self.assertEqual(original.l10n_sk_health_insurer_code, "24")
        self.assertFalse(self.hr_user.has_group("base.group_system"))
        with self.assertRaises(AccessError):
            self.env["hr.version"].with_user(self.hr_user)._l10n_sk_migrate_legacy_insurers()

    @freeze_time("2026-06-15")
    def test_context_default_and_explicit_empty_remain_distinct(self):
        Employee = self.env["hr.employee"].with_company(self.company)
        for insurer in (False, "27"):
            employee = Employee.with_context(
                default_l10n_sk_health_insurer_code=insurer
            ).create({"name": "Synthetic context insuree", "date_version": "2026-01-01"})
            self.assertEqual(employee.version_id.l10n_sk_health_insurer_code, insurer)

    @freeze_time("2026-06-15")
    def test_initial_insurer_comes_from_employee_company(self):
        other = self.env["res.company"].create(
            {"name": "Synthetic other insurer company", "l10n_sk_health_insurer_code": "25"}
        )
        employee = self.env["hr.employee"].with_company(self.company).create(
            {"name": "Synthetic other-company insuree", "company_id": other.id}
        )
        self.assertEqual(employee.version_id.l10n_sk_health_insurer_code, "25")
