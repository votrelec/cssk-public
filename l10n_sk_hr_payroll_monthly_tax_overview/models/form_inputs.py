# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Reviewed form facts, separate from the native payroll calculation."""
import hashlib
import json
import math
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PrehladFormInputs(models.Model):
    _inherit = "l10n.sk.prehlad"

    _form_review_fields = frozenset({
        "form_inputs_reviewed_by", "form_inputs_reviewed_at", "form_inputs_digest"})
    _form_input_fields = frozenset({
        "prepared_on", "correction_discovered_on", "foreign_advance_amount",
        "foreign_receipt_month", "foreign_advance_source", "prior_advance_offset",
        "form_inputs_evidence"})

    prepared_on = fields.Date(
        string="Prepared on", default=fields.Date.context_today, copy=False,
        help="Date written in the overview. It is not the authority's filing date.")
    correction_discovered_on = fields.Date(
        string="Correction discovered on", copy=False, tracking=True,
        help="Actual date the incorrect filed overview was discovered. Enter it from reviewed evidence; it is never inferred from the clock.")
    foreign_advance_amount = fields.Monetary(
        string="Foreign employment advance (row 1a)", copy=False,
        help="Reviewed advance under section 5(4), without the child bonus. This is a reporting fact, not a second payroll calculation.")
    foreign_receipt_month = fields.Date(
        string="Foreign income document received in", copy=False,
        help="Enter the first day of the month when the income document was received. The wire carries MM.YYYY.")
    foreign_advance_source = fields.Selection([
        ("additional", "Additional to native payroll advances"),
        ("included", "Already included in native payroll advances")],
        string="Foreign advance source", copy=False)
    prior_advance_offset = fields.Boolean(
        string="Earlier excess advances offset this month (row 8b)", copy=False,
        help="Tick only when this month's remittance is reduced by advances over-remitted in earlier months under section 40(8). A request for an authority refund is a different event and does not set this box.")
    form_inputs_evidence = fields.Text(string="Form facts evidence", copy=False)
    form_inputs_reviewed_by = fields.Many2one(
        "res.users", string="Form facts reviewed by", readonly=True, copy=False)
    form_inputs_reviewed_at = fields.Datetime(
        string="Form facts reviewed on", readonly=True, copy=False)
    form_inputs_digest = fields.Char(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, values_list):
        if any("default_" + name in self.env.context for name in self._form_review_fields) or any(
                self._form_review_fields.intersection(values) for values in values_list):
            raise UserError(_("Review form facts through the overview action."))
        return super().create(values_list)

    def write(self, values):
        if self._form_review_fields.intersection(values):
            raise UserError(_("Review form facts through the overview action."))
        if (self._form_input_fields | {"company_id", "year", "month", "correction_type"}).intersection(values):
            if any(record.state != "draft" for record in self):
                raise UserError(_("Reset the overview to draft before editing its form facts."))
            values = dict(values, **{name: False for name in self._form_review_fields})
        return super().write(values)

    def _prehlad_form_facts(self):
        """Stable public hook for extensions' source proofs and review digest."""
        self.ensure_one()
        names = self._form_input_fields | {"company_id", "year", "month", "correction_type"}
        return {name: (self[name].id if self._fields[name].type == "many2one"
                       else str(self[name]) if self._fields[name].type == "date"
                       else self[name]) for name in sorted(names)}

    def _prehlad_form_digest(self):
        return hashlib.sha256(json.dumps(self._prehlad_form_facts(), sort_keys=True).encode()).hexdigest()

    def _prehlad_validate_form_facts(self, require_review=True):
        self.ensure_one()
        if not self.prepared_on:
            raise UserError(_("Enter the overview's preparation date."))
        discovered = self.correction_discovered_on
        if self._is_amending_declaration():
            if not discovered:
                raise UserError(_("Enter the actual discovery date for the corrective overview."))
            if not self.prepared_on or not self.date_from <= discovered <= self.prepared_on:
                raise UserError(_("The discovery date must be between the reporting month's first day and the preparation date."))
        elif discovered:
            raise UserError(_("A regular overview must leave the correction discovery date empty."))
        amount = self.foreign_advance_amount
        if not math.isfinite(amount) or amount < 0:
            raise UserError(_("The foreign employment advance must be a finite nonnegative amount."))
        foreign = bool(amount or self.foreign_receipt_month or self.foreign_advance_source)
        if foreign and (not self.foreign_receipt_month or self.foreign_receipt_month.day != 1
                        or not self.foreign_advance_source):
            raise UserError(_("Specify the foreign document receipt month (first day) and whether its advance is already included in payroll."))
        next_month = date(int(self.year) + (int(self.month) == 12), int(self.month) % 12 + 1, 1)
        if self.foreign_receipt_month and self.foreign_receipt_month != next_month:
            raise UserError(_("Report the foreign document receipt in the month following the reporting month."))
        if self.prepared_on and self.foreign_receipt_month and self.foreign_receipt_month > self.prepared_on:
            raise UserError(_("The foreign document receipt month cannot follow the preparation date."))
        active = bool(discovered or foreign or self.prior_advance_offset)
        if active and not (self.form_inputs_evidence or "").strip():
            raise UserError(_("Record the evidence for the overview's conditional form facts."))
        if active and require_review and (not self.form_inputs_reviewed_by
                or self.form_inputs_digest != self._prehlad_form_digest()):
            raise UserError(_("Review the current form facts before generating the overview."))
        return True

    def action_review_form_inputs(self):
        self.check_access("write")
        for record in self:
            if record.company_id not in self.env.companies:
                raise AccessError(_("Review form facts in an allowed company."))
            if record.state != "draft":
                raise UserError(_("Review form facts on a draft overview."))
            record._prehlad_validate_form_facts(require_review=False)
            super(PrehladFormInputs, record).write({
                "form_inputs_reviewed_by": self.env.user.id,
                "form_inputs_reviewed_at": fields.Datetime.now(),
                "form_inputs_digest": record._prehlad_form_digest()})
        return True

    def _preflight(self):
        result = super()._preflight()
        for record in self:
            record._prehlad_validate_form_facts()
        return result

    def _prehlad_advance_rows(self, native_advance):
        """Classify an existing advance or add an externally evidenced one.

        Extensions apply their native corrections first, then use this hook.
        It never writes payroll, tax executions or accounting entries.
        """
        self.ensure_one()
        amount = round(self.foreign_advance_amount, 2)
        domestic = native_advance - amount if self.foreign_advance_source == "included" else native_advance
        if amount and domestic < -.005:
            raise UserError(_("The reclassified foreign advance exceeds the native payroll advance."))
        return round(domestic, 2), amount

    def _prehlad_quarter_month(self, month):
        """Existing monthly facts for refund calculations, without guessing drafts."""
        self.ensure_one()
        if month == int(self.month):
            return self
        record = self.search([
            ("company_id", "=", self.company_id.id), ("year", "=", self.year),
            ("month", "=", str(month)), ("state", "in", ("generated", "submitted"))],
            order="state desc, submitted_date desc, id desc", limit=1)
        if record and (record.foreign_advance_amount or record.foreign_receipt_month):
            record._prehlad_validate_form_facts()
        return record or self.new({"company_id": self.company_id.id,
                                  "year": self.year, "month": str(month),
                                  "prepared_on": self.prepared_on})

    def _prehlad_quarter_inputs(self, month):
        record = self._prehlad_quarter_month(month)
        return {name: record[name] for name in (
            "foreign_advance_amount", "foreign_advance_source", "foreign_receipt_month",
            "prepared_on", "form_inputs_evidence")}

    def action_reset_to_draft(self):
        result = super().action_reset_to_draft()
        for record in self:
            super(PrehladFormInputs, record).write({name: False for name in self._form_review_fields})
        return result

    def copy(self, default=None):
        default = dict(default or {})
        default.update(state="draft", xml_attachment_id=False)
        return super().copy(default)
