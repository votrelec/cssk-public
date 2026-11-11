# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Coordinate relevant Slovak fund sources under REPEATABLE READ.

The request layer retries serialization failures. Imports, scheduled jobs and
standalone scripts must retry their whole transaction themselves. Providers
with additional source fields extend the cooperative field-name hook below.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Employee(models.Model):
    _inherit = "hr.employee"

    l10n_sk_fund_source_epoch = fields.Integer(
        string="Payroll source version", default=0, readonly=True, copy=False
    )

    @api.model_create_multi
    def create(self, values_list):
        if "default_l10n_sk_fund_source_epoch" in self.env.context or any(
            "l10n_sk_fund_source_epoch" in values for values in values_list
        ):
            raise UserError(_("Payroll fund source coordination is internal."))
        return super().create(values_list)

    def write(self, values):
        if "l10n_sk_fund_source_epoch" in values:
            raise UserError(_("Payroll fund source coordination is internal."))
        if {
            "company_id",
            "identification_id",
            "l10n_sk_health_insurer_code",
        } & values.keys():
            self.check_access("write")
            self._l10n_sk_lock_fund_source()
        return super().write(values)

    def _l10n_sk_lock_fund_source(self):
        """Serialize SK sources; non-request callers retry whole transactions."""
        self.check_access("read")
        sources = self.filtered(
            lambda employee: employee.company_id.country_id.code == "SK"
        )
        if not sources:
            return
        sources.flush_recordset(["l10n_sk_fund_source_epoch"])
        self.env.cr.execute(
            "SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR NO KEY UPDATE",
            [tuple(sorted(sources.ids))],
        )
        self.env.cr.execute(
            "UPDATE hr_employee SET l10n_sk_fund_source_epoch="
            "COALESCE(l10n_sk_fund_source_epoch,0)+1 WHERE id IN %s",
            [tuple(sorted(sources.ids))],
        )
        sources.invalidate_recordset(["l10n_sk_fund_source_epoch"])

    def _l10n_sk_lock_social_source(self):
        """Compatibility name; all writers now coordinate the same fund source."""
        return self._l10n_sk_lock_fund_source()


class Version(models.Model):
    _inherit = "hr.version"

    @api.model
    def _l10n_sk_fund_source_field_names(self):
        return frozenset(
            {
                "employee_id",
                "company_id",
                "date_version",
                "contract_date_start",
                "contract_date_end",
                "resource_calendar_id",
                "wage",
                "struct_id",
                "structure_type_id",
                "identification_id",
                "l10n_sk_hourly_wage",
                "l10n_sk_agreement_type",
                "l10n_sk_income_regular",
                "l10n_sk_pension_type",
                "l10n_sk_agreement_oop",
                "l10n_sk_guarantee_exempt",
                "l10n_sk_ztp",
                "l10n_sk_health_exempt",
                "l10n_sk_health_oop_claim",
                "l10n_sk_health_minimum_opt_out",
                "l10n_sk_health_minimum_evidence",
                "l10n_sk_tax_declaration_signed",
                "l10n_sk_children_under_15",
                "l10n_sk_children_15_18",
                "l10n_sk_tax_pensioner",
                "l10n_sk_nczd_pension_annual",
            }
        )

    @api.model_create_multi
    def create(self, values_list):
        self.check_access("create")
        defaults = self.default_get(["employee_id"])
        ids = {
            values.get("employee_id", defaults.get("employee_id"))
            for values in values_list
        }
        self.env["hr.employee"].browse(
            sorted(identifier for identifier in ids if identifier)
        )._l10n_sk_lock_fund_source()
        return super().create(values_list)

    def write(self, values):
        if not self._l10n_sk_fund_source_field_names().intersection(values):
            return super().write(values)
        self.check_access("write")
        employees = self.employee_id | self.env["hr.employee"].browse(
            values.get("employee_id")
        )
        employees._l10n_sk_lock_fund_source()
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self.employee_id._l10n_sk_lock_fund_source()
        return super().unlink()


class HealthCalendarSource(models.Model):
    _inherit = "l10n.sk.health.calendar"

    @api.model_create_multi
    def create(self, values_list):
        self.check_access("create")
        defaults = self.default_get(["employee_id"])
        identifiers = {
            values.get("employee_id", defaults.get("employee_id"))
            for values in values_list
        }
        self.env["hr.employee"].browse(
            sorted(x for x in identifiers if x)
        )._l10n_sk_lock_fund_source()
        return super().create(values_list)

    def _lock_for_change(self):
        self.employee_id._l10n_sk_lock_fund_source()
        return super()._lock_for_change()

    def write(self, values):
        if values.get("employee_id"):
            (
                self.employee_id | self.env["hr.employee"].browse(values["employee_id"])
            )._l10n_sk_lock_fund_source()
        return super().write(values)
