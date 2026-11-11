# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# ÚDZS common health-insurer codes (kód zdravotnej poisťovne).
HEALTH_INSURER_CODES = [
    ("25", "VšZP (25)"),
    ("24", "Dôvera (24)"),
    ("27", "Union (27)"),
]

PAYER_FIELDS = {
    "25": "l10n_sk_health_payer_vszp",
    "24": "l10n_sk_health_payer_dovera",
    "27": "l10n_sk_health_payer_union",
}


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_sk_health_insurer_code = fields.Selection(
        HEALTH_INSURER_CODES,
        string="Health insurer (dávka 514)",
        default="25",
        help="Target health insurance company for the monthly dávka 514. "
        "The dávka 514 structure is common to all "
        "three insurers; only this code and the payer/bank details differ.")
    l10n_sk_health_payer_number = fields.Char(
        string="Health payer number",
        help="Payer number assigned to the employer by the health insurer — "
        "the payer-number item of the dávka 514 identification block.")

    l10n_sk_health_payer_vszp = fields.Char(string="VšZP payer number")
    l10n_sk_health_payer_dovera = fields.Char(string="Dôvera payer number")
    l10n_sk_health_payer_union = fields.Char(string="Union payer number")

    def _l10n_sk_health_payer_for_insurer(self, insurer):
        self.ensure_one()
        field = PAYER_FIELDS.get(insurer)
        explicit = self[field] if field else False
        return explicit or (
            self.l10n_sk_health_payer_number
            if insurer == self.l10n_sk_health_insurer_code else False
        )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        keys = set(PAYER_FIELDS.values()) | {"l10n_sk_health_payer_number"}
        for company, values in zip(companies, vals_list):
            provided = {name: value for name, value in values.items() if name in keys}
            if provided:
                company.write(provided)
        return companies

    def write(self, values):
        legacy = "l10n_sk_health_payer_number"
        selector = "l10n_sk_health_insurer_code"
        if not (set(PAYER_FIELDS.values()) | {legacy, selector}).intersection(values):
            return super().write(values)
        changes = []
        for company in self:
            updated = dict(values)
            old = PAYER_FIELDS.get(company.l10n_sk_health_insurer_code)
            chosen = values.get(selector, company.l10n_sk_health_insurer_code)
            current = PAYER_FIELDS.get(chosen)
            if chosen != company.l10n_sk_health_insurer_code:
                if old and not company[old] and company[legacy]:
                    updated.setdefault(old, company[legacy])
                if legacy not in updated:
                    updated[legacy] = updated.get(current, company[current] if current else False)
            if current:
                if legacy in updated and current in updated:
                    left = "".join(str(updated[legacy] or "").split())
                    right = "".join(str(updated[current] or "").split())
                    if left != right:
                        raise ValidationError(_(
                            "The default payer number must match the configured number of the default insurer."
                        ))
                if current in updated:
                    updated[legacy] = updated[current]
                elif legacy in updated:
                    updated[current] = updated[legacy]
            changes.append((company, updated))
        for company, updated in changes:
            super(ResCompany, company).write(updated)
        return True

    @api.model
    def _l10n_sk_migrate_health_payer_settings(self):
        if not self.env.su:
            raise AccessError("Payer settings migration requires the upgrade environment.")
        for company in self.search([("l10n_sk_health_payer_number", "!=", False)]):
            field = PAYER_FIELDS.get(company.l10n_sk_health_insurer_code)
            if field:
                company.write({field: company[field] or company.l10n_sk_health_payer_number})
