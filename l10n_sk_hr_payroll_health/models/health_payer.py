# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Freeze the selected insurer's payer identity on its own statement."""

import base64

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class HealthPayer(models.Model):
    _inherit = "l10n.sk.health"

    payer_number = fields.Char(
        string="Health payer number", compute="_compute_health_payer_number",
        store=True, readonly=False, copy=True, related=False,
        help="Number assigned by this statement's insurer. Initialised from the insurer's "
        "company setting, then retained with the statement when company settings change.",
    )

    @api.depends("company_id", "insurer_code")
    def _compute_health_payer_number(self):
        for statement in self:
            statement.payer_number = statement.company_id._l10n_sk_health_payer_for_insurer(
                statement.insurer_code
            ) if statement.company_id else False

    def _legacy_fund_report_inputs(self):
        result = super()._legacy_fund_report_inputs()
        result["payer_number"] = self.payer_number
        return result

    def write(self, values):
        names = {
            "payer_number", "company_id", "insurer_code", "year", "month",
            "payment_date", "version_id", "correction_type", "correction_reference", "export_format",
        }.intersection(values)
        for statement in self:
            if statement.state == "draft":
                continue
            for name in names:
                previous = statement[name]
                incoming = values[name]
                field = statement._fields[name]
                if field.type == "many2one":
                    previous = previous.id
                    if isinstance(incoming, (list, tuple)):
                        incoming = incoming[0] if incoming else False
                elif field.type == "date":
                    incoming = fields.Date.to_date(incoming) or False
                    previous = previous or False
                elif field.type in {"char", "text"}:
                    incoming, previous = incoming or False, previous or False
                if previous != incoming:
                    if name == "export_format":
                        raise UserError(_("Reset the declaration to draft before changing its export format."))
                    raise UserError(_(
                        "Reset the declaration to draft before changing its filing inputs."
                    ))
        frozen = self.filtered(lambda statement: statement.state != "draft")
        if names and frozen:
            # Even an unchanged dependency write can schedule a stored
            # recomputation. Do not refresh a filed payer from today's config.
            mutable = self - frozen
            result = super(HealthPayer, mutable).write(values) if mutable else True
            remaining = {key: value for key, value in values.items() if key not in names}
            if remaining:
                result = super(HealthPayer, frozen).write(remaining) and result
            return result
        return super().write(values)

    @api.model
    def _l10n_sk_migrate_legacy_payer_numbers(self):
        """Use retained bytes, never today's payer setting for an old file."""
        if not self.env.su:
            raise AccessError("Payer migration requires the upgrade environment.")
        for statement in self.search([]):
            attachment = statement.xml_attachment_id or statement.submitted_attachment_id
            if not attachment:
                continue
            payload = base64.b64decode(attachment.with_context(bin_size=False).datas or b"")
            try:
                if payload.lstrip().startswith(b"<"):
                    root = etree.fromstring(payload, parser=etree.XMLParser(
                        resolve_entities=False, no_network=True,
                    ))
                    payer = root.findtext("Identification/CodeOfPayer")
                else:
                    header = payload.decode("utf-8").splitlines()[0].split("|")
                    payer = header[3] if len(header) == 11 and header[1] == "514" else False
            except (UnicodeError, IndexError, etree.XMLSyntaxError):
                payer = False
            if not payer or len(payer) != 10 or any(ch not in "0123456789" for ch in payer):
                payer = False
            # Only the private superuser upgrade method bypasses this model's
            # generated-input guard. Keep all other inherited write hooks.
            super(HealthPayer, statement).write({"payer_number": payer})
