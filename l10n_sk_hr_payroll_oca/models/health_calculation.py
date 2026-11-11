# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Validate source facts before safe_eval, retain their common profile once."""

from odoo import _, models
from odoo.exceptions import UserError


class HealthCalculationPayslip(models.Model):
    _inherit = "hr.payslip"

    def compute_sheet(self):
        for slip in self:
            for version in slip.contract_id or slip._get_employee_contracts():
                calendar = version._l10n_sk_health_calendar_context(slip.date_from)
                if version.l10n_sk_health_minimum_opt_out:
                    version.l10n_sk_health_minimum_is_opted_out()
                    if not calendar:
                        raise UserError(
                            _(
                                "Review a health calendar proving concurrent employers before applying the minimum opt-out."
                            )
                        )
        return super().compute_sheet()

    def _l10n_sk_fund_profile(self):
        result = super()._l10n_sk_fund_profile()
        version = self._l10n_sk_version()
        result["health"] = version._l10n_sk_health_profile(self.date_from)
        return result
