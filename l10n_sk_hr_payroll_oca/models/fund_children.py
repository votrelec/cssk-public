# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, models
from odoo.exceptions import UserError


class FundSourceChild(models.AbstractModel):
    _name = "l10n.sk.fund.source.child"
    _description = "Retained payroll fund source protection"

    def _l10n_sk_fund_parents(self, values=None, include_existing=True):
        parents = (
            self[self._fund_parent_field]
            if include_existing
            else self.env["hr.payslip"]
        )
        if values is not None:
            identifier = values.get(
                self._fund_parent_field,
                self.env.context.get("default_" + self._fund_parent_field),
            )
            parents |= self.env["hr.payslip"].browse(identifier)
        return parents

    def _l10n_sk_check_fund_parents(self, parents):
        parents._l10n_sk_lock_fund_payslips()
        if any(slip._l10n_sk_fund_is_protected() for slip in parents):
            raise UserError(
                _("Retain confirmed payroll fund sources; use a payroll correction.")
            )

    @api.model_create_multi
    def create(self, values_list):
        self.check_access("create")
        parents = self.env["hr.payslip"]
        for values in values_list:
            # copy() calls create() on the original nonempty child recordset.
            # A create checks the new/default parent only, never that original.
            parents |= self._l10n_sk_fund_parents(values, include_existing=False)
        self._l10n_sk_check_fund_parents(parents)
        return super().create(values_list)

    def write(self, values):
        self.check_access("write")
        self._l10n_sk_check_fund_parents(self._l10n_sk_fund_parents(values))
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self._l10n_sk_check_fund_parents(self._l10n_sk_fund_parents())
        return super().unlink()


class Input(models.Model):
    _name = "hr.payslip.input"
    _inherit = ["hr.payslip.input", "l10n.sk.fund.source.child"]
    _fund_parent_field = "payslip_id"


class WorkedDay(models.Model):
    _name = "hr.payslip.worked_days"
    _inherit = ["hr.payslip.worked_days", "l10n.sk.fund.source.child"]
    _fund_parent_field = "payslip_id"


class SalaryLine(models.Model):
    _name = "hr.payslip.line"
    _inherit = ["hr.payslip.line", "l10n.sk.fund.source.child"]
    _fund_parent_field = "slip_id"
