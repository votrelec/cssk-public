# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Validate explicit exemption inputs before the salary-rule evaluator."""

from odoo import models


class HealthExemptionPayslip(models.Model):
    _inherit = "hr.payslip"

    def compute_sheet(self):
        # A missing legal basis is an actionable business error. Validate it
        # before safe_eval wraps exceptions as a salary-rule programming error.
        # Statutory agreement exclusions still need no individual checkbox.
        for slip in self:
            versions = slip.contract_id or slip._get_employee_contracts()
            for version in versions:
                if version.l10n_sk_health_exempt:
                    version.l10n_sk_health_is_exempt()
        return super().compute_sheet()
