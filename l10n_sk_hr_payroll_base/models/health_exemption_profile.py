# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dated health exclusion facts, independent of the payroll engine."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..health_exemption import (
    agreement_health_exempt,
    pension_state_insured,
    pension_health_disabled,
)


class HealthExemptionProfile(models.Model):
    _inherit = "hr.version"

    l10n_sk_health_exempt_evidence = fields.Char(
        string="Individual health exemption basis and reference",
        help="Retain the individually reviewed legal basis, such as applicable foreign coverage. State-insured status alone does not exclude ordinary employment income.",
    )

    @api.model
    def _get_whitelist_fields_from_template(self):
        values = super()._get_whitelist_fields_from_template() or []
        name = "l10n_sk_health_exempt_evidence"
        return values + ([name] if name not in values else [])

    def l10n_sk_health_is_exempt(self):
        self.ensure_one()
        if agreement_health_exempt(
            self.l10n_sk_employment_form(), self.l10n_sk_pension_status()
        ):
            return True
        if not getattr(self, "l10n_sk_health_exempt", False):
            return False
        if not (self.l10n_sk_health_exempt_evidence or "").strip():
            raise UserError(
                _(
                    "Retain the individual legal basis for excluding health premiums. State-insured status alone does not exclude ordinary employment income."
                )
            )
        return True

    def l10n_sk_health_is_disabled(self):
        self.ensure_one()
        return bool(
            getattr(self, "l10n_sk_ztp", False)
            or pension_health_disabled(self.l10n_sk_pension_status())
        )

    def l10n_sk_health_minimum_is_exempt(self):
        """Separate an excluded receipt from a state insuree's minimum relief.

        Calendar-based partial-month exceptions are a separate calculation
        contribution; this method resolves the dated pension/disabled profile.
        """
        self.ensure_one()
        return bool(
            self.l10n_sk_health_is_exempt()
            or self.l10n_sk_health_is_disabled()
            or pension_state_insured(self.l10n_sk_pension_status())
        )
