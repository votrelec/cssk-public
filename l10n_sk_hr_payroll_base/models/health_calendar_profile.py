# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Read reviewed calendar facts without changing any payroll calculation."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..health_exemption import pension_health_disabled


class HealthCalendarProfile(models.Model):
    _inherit = "hr.version"

    l10n_sk_health_minimum_opt_out = fields.Boolean(
        string="Concurrent-employment minimum opt-out",
        help="Section 16a(5): written notice of concurrent employers. This is separate from state-insured status or disability.",
    )
    l10n_sk_health_minimum_evidence = fields.Char(
        string="Minimum opt-out notice reference",
        help="Retained written notice and concurrent-employment facts for this version.",
    )

    @api.model
    def _get_whitelist_fields_from_template(self):
        values = super()._get_whitelist_fields_from_template() or []
        return values + [
            name
            for name in (
                "l10n_sk_health_minimum_opt_out",
                "l10n_sk_health_minimum_evidence",
            )
            if name not in values
        ]

    def l10n_sk_health_minimum_is_opted_out(self):
        self.ensure_one()
        if (
            self.l10n_sk_health_minimum_opt_out
            and not (self.l10n_sk_health_minimum_evidence or "").strip()
        ):
            raise UserError(
                _(
                    "Record the employee's written concurrent-employment minimum opt-out notice before calculation."
                )
            )
        return bool(self.l10n_sk_health_minimum_opt_out)

    def _l10n_sk_health_calendar_context(self, day):
        """Read the reviewed month; a replacement draft is never new evidence.

        Both engines and the registration/declaration adapters can consume this
        factual API. This contribution does not alter salary rules or amounts.
        """
        self.ensure_one()
        self.check_access("read")
        month = fields.Date.to_date(day).replace(day=1)
        calendar = self.env["l10n.sk.health.calendar"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("employee_id", "=", self.employee_id.id),
                ("month", "=", month),
                ("state", "!=", "superseded"),
            ]
        )
        if calendar and calendar.state != "reviewed":
            raise UserError(
                _("Finish reviewing the employee's health calendar before calculation.")
            )
        facts = calendar._calendar_context() if calendar else False
        if (
            facts
            and (
                getattr(self, "l10n_sk_ztp", False)
                or pension_health_disabled(self.l10n_sk_pension_status())
            )
            and not facts["disability_in_month"]
        ):
            raise UserError(
                _(
                    "Review the disability disagreement between the employment version and the health calendar."
                )
            )
        if facts and self.l10n_sk_health_minimum_opt_out:
            self.l10n_sk_health_minimum_is_opted_out()
            if not facts["concurrent_other_employment"]:
                raise UserError(
                    _(
                        "A minimum opt-out requires concurrent employers in the reviewed health calendar."
                    )
                )
        return facts
