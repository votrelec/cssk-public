# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Keep upstream employee locks ahead of accounting's payslip-row guard."""
from odoo import models


class PayrollSourceLockOrder(models.Model):
    _inherit = "hr.payslip"

    def _lock_payroll_sources(self):
        # Older engines have no pre-lock extension point. Their native
        # calculation remains supported; the accounting adapter uses this hook
        # when running with the cooperative engine contribution.
        parent = getattr(super(), "_lock_payroll_sources", None)
        if parent:
            parent()
        self._l10n_sk_lock_fund_payslips()
