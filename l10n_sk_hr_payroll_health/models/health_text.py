# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Offer the published 514 text format through the common filing workflow."""

from odoo import _, fields, models
from odoo.exceptions import UserError

from .. import text514


class HealthText(models.Model):
    _inherit = "l10n.sk.health"

    # Section 2(4), decree 159/2018: O replaces the full filing and can
    # correct every section 1 item. A is a difference under section 2(5),
    # so the full-state collector must not offer it as another full month.
    _supported_correction_types = ("regular", "corrective")

    export_format = fields.Selection(
        [("xml", "XML"), ("text514", "Text batch 514")],
        string="Export format", default="xml", required=True, tracking=True,
    )

    def _render_xml(self, data):
        if self.export_format != "text514":
            return super()._render_xml(data)
        context = self._declaration_render_context(data)
        ident, corp = context["ident"], context["corp"]
        employer = self.company_id
        try:
            return text514.render(
                {
                    "characteristic": ident["charakter"], "ico": ident["ico"],
                    "payer": ident["cislo_platitela"], "insurer": ident["kod_zp"],
                    "sent_on": ident["datum_odoslania"], "sequence": 1,
                },
                {
                    "period": corp["obdobie"].replace("-", ""),
                    "payment_day": (self.payment_date or self.date_to).day,
                    "name": corp["nazov"], "dic": corp["dic"], "iban": corp["iban"],
                    "phone": employer.phone or "", "email": employer.email or "",
                    "legal_form": "PO" if employer.partner_id.is_company else "FO",
                },
                context["health514_summary"], context["health514_wire_rows"],
            )
        except ValueError as exc:
            raise UserError(_(
                "Review the employer identification, bank account and recorded health rows "
                "against the published 514 text format before generating the batch."
            )) from exc

    def _validate_against_schema(self, payload):
        if self.export_format != "text514":
            return super()._validate_against_schema(payload)
        # The typed codec has validated every field, count and monetary total
        # while rendering. A text batch is not an XML/XSD instance.
        try:
            text = payload.decode("utf-8")
        except UnicodeError as exc:
            raise UserError(_("The 514 text batch must be valid UTF-8.")) from exc
        if not text or not text.endswith("|\r\n") or "|514|" not in text.splitlines()[0]:
            raise UserError(_("The generated 514 text batch has an invalid record structure."))
        return True

    def _declaration_attachment_name(self):
        if self.export_format == "text514":
            characteristic = {
                "regular": "N", "corrective": "O", "supplementary": "A",
            }[self.correction_type]
            return text514.filename(characteristic, "%04d%02d" % (int(self.year), int(self.month)), 1)
        return super()._declaration_attachment_name()

    def _declaration_attachment_mimetype(self):
        if self.export_format == "text514":
            return "text/plain"
        return super()._declaration_attachment_mimetype()

    def _declaration_generated_message(self):
        return _("Dávka 514 generated and format-validated. Retain the insurer's receipt separately.")
