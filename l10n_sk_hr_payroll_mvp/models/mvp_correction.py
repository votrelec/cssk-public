# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Full electronic replacement, using the common declaration lifecycle."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Mvp(models.Model):
    _inherit = "l10n.sk.mvp"
    _supported_correction_types = ("regular", "corrective")

    replaced_mvp_id = fields.Many2one(
        "l10n.sk.mvp",
        string="Replaces filed MVP",
        ondelete="restrict",
        copy=False,
        check_company=True,
    )

    def _retained_prior_mvp(self):
        self.ensure_one()
        return self._prior_submitted().filtered(
            lambda prior: prior.submitted_attachment_id
            and prior.submitted_attachment_id in prior.filed_history_ids
        )

    def _prefill_replaced_mvp(self):
        for report in self.filtered(
            lambda rec: rec.correction_type == "corrective" and not rec.replaced_mvp_id
        ):
            candidates = report._retained_prior_mvp()
            if len(candidates) == 1:
                report.replaced_mvp_id = candidates

    @api.onchange("correction_type", "company_id", "year", "month")
    def _onchange_replaced_mvp(self):
        for report in self:
            if report.correction_type != "corrective":
                report.replaced_mvp_id = False
            elif (
                not report.replaced_mvp_id
                or report.replaced_mvp_id not in report._retained_prior_mvp()
            ):
                report.replaced_mvp_id = False
                report._prefill_replaced_mvp()

    @api.model_create_multi
    def create(self, values_list):
        reports = super().create(values_list)
        for report, values in zip(reports, values_list):
            if (
                "replaced_mvp_id" not in values
                and "default_replaced_mvp_id" not in self.env.context
            ):
                report._prefill_replaced_mvp()
        return reports

    def copy_data(self, default=None):
        values = dict(default or {})
        # copy=False alone omits the field, which would trigger automatic
        # single-candidate selection in create(). A copy starts unreviewed.
        values.setdefault("replaced_mvp_id", False)
        return super().copy_data(values)

    def write(self, values):
        identity = {
            "company_id",
            "year",
            "month",
            "version_id",
            "payment_date",
            "date_from",
            "date_to",
            "correction_type",
            "correction_reference",
            "replaced_mvp_id",
        }
        if identity & values.keys() and any(report.state != "draft" for report in self):
            raise UserError(
                _(
                    "Reset the MVP to draft before changing its period or correction identity. "
                    "The filed copy is retained."
                )
            )
        result = super().write(values)
        if {"correction_type", "company_id", "year", "month"} & values.keys():
            if "replaced_mvp_id" not in values:
                self._prefill_replaced_mvp()
        return result

    def _preflight(self):
        result = super()._preflight()
        for report in self:
            prior = report.replaced_mvp_id
            if report.correction_type == "regular":
                if prior:
                    raise UserError(
                        _(
                            "A regular MVP cannot replace a filed MVP. Select Corrective."
                        )
                    )
            elif not prior or prior not in report._retained_prior_mvp():
                raise UserError(
                    _(
                        "Choose the retained filed MVP for this exact company and payroll period."
                    )
                )
        return result

    def _declaration_render_context(self, data):
        context = super()._declaration_render_context(data)
        # Keep the native complete source selection and fund calculations.
        # O replaces the entire electronic filing; it is never a delta.
        context["typ_vykazu"] = "O" if self.correction_type == "corrective" else "R"
        return context
