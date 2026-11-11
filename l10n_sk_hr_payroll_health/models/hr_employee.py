# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    l10n_sk_health_insurer_code = fields.Selection(
        related="version_id.l10n_sk_health_insurer_code",
        readonly=False,
        inherited=True,
        string="Health insurer (SK)",
        groups="hr.group_hr_user",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # HR creates the delegated version before linking the employee to it.
        # Supply the initial value through native _inherits rather than trying
        # to infer an employee from the not-yet-linked version.
        values = []
        for vals in vals_list:
            vals = dict(vals)
            if (
                "l10n_sk_health_insurer_code" not in vals
                and "default_l10n_sk_health_insurer_code" not in self.env.context
            ):
                company = self.env["res.company"].browse(
                    vals.get("company_id")
                    or self.env.context.get("default_company_id")
                    or self.env.company.id
                )
                vals["l10n_sk_health_insurer_code"] = company.l10n_sk_health_insurer_code
            values.append(vals)
        return super().create(values)

    def _l10n_sk_health_insurer(self):
        """The employee's insurer, falling back to the company default."""
        self.ensure_one()
        return (self.sudo().l10n_sk_health_insurer_code
                or self.company_id.l10n_sk_health_insurer_code)
