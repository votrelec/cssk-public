# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Quarter evidence belongs to the retained XML, not the editable draft."""
import base64
import copy
import hashlib
import math
from contextvars import ContextVar
from datetime import datetime

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_RETENTION_OPERATION = ContextVar("prehlad_retention_operation", default=False)


class PrehladCompanyEpoch(models.Model):
    _inherit = "res.company"

    prehlad_filing_epoch = fields.Integer(readonly=True, copy=False, default=0)


class PrehladFiledFacts(models.Model):
    _inherit = "l10n.sk.prehlad"

    _prehlad_snapshot_fields = frozenset({"generated_form_facts", "filed_form_facts"})
    _prehlad_retention_fields = frozenset({"submitted_attachment_id", "filed_history_ids", "submitted_date"})
    generated_form_facts = fields.Json(readonly=True, copy=False)
    filed_form_facts = fields.Json(readonly=True, copy=False)
    legacy_filed_foreign_source = fields.Selection([
        ("additional", "Additional to native payroll advances"),
        ("included", "Already included in native payroll advances")],
        string="Archived foreign advance source", copy=False)
    legacy_filed_premium_own = fields.Monetary(
        string="Archived employee premium paid from own funds", copy=False)
    legacy_filed_evidence = fields.Text(string="Archived form facts evidence", copy=False)
    legacy_filed_order = fields.Integer(
        string="Reviewed archived filing order", copy=False,
        help="Relative order of archived filings for this company and month, from reviewed evidence. Only needed when old local timestamps cannot distinguish their order; not an authority reference.")

    @api.model_create_multi
    def create(self, values_list):
        if (any("default_" + name in self.env.context for name in self._prehlad_retention_fields)
                or self.env.context.get("default_state", "draft") != "draft"
                or any(self._prehlad_retention_fields.intersection(values) or values.get("state", "draft") != "draft"
                       for values in values_list)):
            raise UserError(_("Use the native overview actions to record or reset a filing."))
        if any("default_" + name in self.env.context for name in self._prehlad_snapshot_fields) or any(
                self._prehlad_snapshot_fields.intersection(values) for values in values_list):
            raise UserError(_("Generate or record a filing to retain its form facts."))
        return super().create(values_list)

    def write(self, values):
        if not _RETENTION_OPERATION.get() and (self._prehlad_retention_fields.intersection(values)
                or ("state" in values and any(record.state != values["state"] for record in self))):
            raise UserError(_("Use the native overview actions to record or reset a filing."))
        if self._prehlad_snapshot_fields.intersection(values):
            raise UserError(_("Generate or record a filing to retain its form facts."))
        for record in self:
            if record.filed_form_facts or record.submitted_attachment_id or record.filed_history_ids:
                if any(name in values and values[name] != (record[name].id if name == "company_id" else record[name])
                       for name in ("company_id", "year", "month")):
                    raise UserError(_("Copy the filed overview to prepare a different company or reporting period."))
        return super().write(values)

    def _prehlad_lock_scope(self):
        """All allowed companies, then all parents, before export children.

        A real company-row update makes a waiting REPEATABLE READ transaction
        retry instead of retaining the pre-filing quarter snapshot. This is
        private to Prehľad operations; other declarations are not changed.
        """
        if not self:
            return
        self.check_access("write")
        companies = self.company_id.sorted("id")
        companies.check_access("read")
        if companies - self.env.companies:
            raise AccessError(_("Use an allowed company for the overview's filing facts."))
        self.flush_recordset()
        for company in companies:
            self.env.cr.execute("UPDATE res_company SET prehlad_filing_epoch = COALESCE(prehlad_filing_epoch, 0) + 1 WHERE id = %s", [company.id])
        self.env.cr.execute("SELECT id FROM l10n_sk_prehlad WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(sorted(self.ids))])
        self.invalidate_recordset()
        self.check_access("write")
        if self.company_id - companies:
            raise UserError(_("The overview scope changed; retry the complete operation."))

    def _prehlad_snapshot_extra(self):
        """Extensions retain their existing source proof, never a new ledger."""
        return {}

    def _prehlad_snapshot_components(self, root):
        return {"child": float(root.findtext("telo/cast2/rC") or 0),
                "interest": float(root.findtext("telo/cast2/rF") or 0), "premium": 0.0}

    def _prehlad_legacy_snapshot_extra(self, xml_hash):
        return {}

    def _prehlad_snapshot(self, attachment, legacy=False):
        self.ensure_one()
        raw = base64.b64decode(attachment.with_context(bin_size=False).datas)
        root = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        xml_hash = hashlib.sha256(raw).hexdigest()
        facts = self._prehlad_form_facts()
        extra = self._prehlad_legacy_snapshot_extra(xml_hash) if legacy else self._prehlad_snapshot_extra()
        if legacy:
            # Wire values survive reset/edit. In particular, do not invent
            # included/additional classification from today's mutable draft.
            receipt = root.findtext("telo/cast1/r01a/mesiacRok")
            discovered = root.findtext("hlavicka/datumZisteniaOP")
            prepared = root.findtext("vyhotovil/datumVyhotovenia")
            facts = {"company_id": self.company_id.id,
                "year": root.findtext("hlavicka/zdanovacieObdobie/rok"),
                "month": root.findtext("hlavicka/zdanovacieObdobie/mesiac"),
                "correction_type": "corrective" if root.findtext("hlavicka/druhPrehladu/opravny") == "1" else "regular",
                "foreign_advance_amount": float(root.findtext("telo/cast1/r01a/suma") or 0),
                "foreign_receipt_month": str(datetime.strptime(receipt, "%m.%Y").date()) if receipt else "False",
                "foreign_advance_source": False,
                "correction_discovered_on": str(datetime.strptime(discovered, "%d.%m.%Y").date()) if discovered else "False",
                "prepared_on": str(datetime.strptime(prepared, "%d.%m.%Y").date()) if prepared else "False",
                "prior_advance_offset": root.findtext("telo/cast1/r08b") == "1",
                "form_inputs_evidence": ""}
            retained = extra.get("form_facts")
            if retained:
                facts = copy.deepcopy(retained)
        components = self._prehlad_snapshot_components(root) if not legacy else {
            "child": float(root.findtext("telo/cast2/rC") or 0),
            "interest": float(root.findtext("telo/cast2/rF") or 0), "premium": 0.0}
        components.update(extra.get("quarter_components", {}))
        return {"format": 1, "report_id": self.id, "company_id": self.company_id.id,
                "year": root.findtext("hlavicka/zdanovacieObdobie/rok"),
                "month": root.findtext("hlavicka/zdanovacieObdobie/mesiac"),
                "attachment_id": attachment.id, "xml_sha256": xml_hash,
                "form_facts": facts, "quarter_components": components,
                "extension_source": extra, "legacy": legacy, "local_filing_sequence": 0}

    def _prehlad_check_snapshot(self, snapshot):
        self.ensure_one()
        attachment = self.env["ir.attachment"].browse(snapshot.get("attachment_id")).exists()
        if (snapshot.get("report_id") != self.id or snapshot.get("company_id") != self.company_id.id
                or snapshot.get("year") != self.year or snapshot.get("month") != self.month
                or not attachment or attachment.res_model != self._name or attachment.res_id != self.id
                or hashlib.sha256(base64.b64decode(attachment.with_context(bin_size=False).datas)).hexdigest() != snapshot.get("xml_sha256")):
            raise UserError(_("The retained overview facts do not match their archived XML."))
        return copy.deepcopy(snapshot)

    def _attach_xml(self, xml_bytes):
        result = super()._attach_xml(xml_bytes)
        super(PrehladFiledFacts, self).write({"generated_form_facts": self._prehlad_snapshot(self.xml_attachment_id)})
        return result

    def action_generate(self):
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            token = _RETENTION_OPERATION.set(True)
            try:
                return super().action_generate()
            finally:
                _RETENTION_OPERATION.reset(token)

    def action_submit(self):
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            snapshots = {}
            previous = {}
            for record in self:
                snapshot = record.generated_form_facts
                if not snapshot:
                    raise UserError(_("Regenerate the current overview before recording its filing facts."))
                snapshot = record._prehlad_check_snapshot(snapshot)
                if snapshot["attachment_id"] != record.xml_attachment_id.id:
                    raise UserError(_("Regenerate the current overview before recording its filing facts."))
                snapshots[record.id] = snapshot
                old = record.filed_form_facts
                if not old and record.submitted_attachment_id:
                    old = record._prehlad_snapshot(record.submitted_attachment_id, legacy=True)
                previous[record.id] = record._prehlad_check_snapshot(old) if old else None
            token = _RETENTION_OPERATION.set(True)
            try:
                result = super().action_submit()
            finally:
                _RETENTION_OPERATION.reset(token)
            for record in self:
                snapshot = snapshots[record.id]
                snapshot["local_filing_sequence"] = record._prehlad_next_filing_sequence()
                snapshot["submitted_on"] = str(record.submitted_date)
                old = previous[record.id]
                history = old.pop("previous_filed_facts", []) if old else []
                if old:
                    history.append(old)
                snapshot["previous_filed_facts"] = history
                super(PrehladFiledFacts, record).write({"filed_form_facts": snapshot})
            return result

    def _prehlad_next_filing_sequence(self):
        return int(self.env.ref(
            "l10n_sk_hr_payroll_monthly_tax_overview.prehlad_local_filing_sequence").next_by_id())

    def action_reset_to_draft(self):
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            token = _RETENTION_OPERATION.set(True)
            try:
                return super().action_reset_to_draft()
            finally:
                _RETENTION_OPERATION.reset(token)

    def unlink(self):
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            if any(record.filed_form_facts or record.submitted_attachment_id or record.filed_history_ids
                   for record in self):
                raise UserError(_("An overview with filed history cannot be deleted. Preserve it and prepare a correction."))
            return super().unlink()

    def _prehlad_quarter_retained(self, month):
        """Last actual local filing wins, irrespective of today's draft state."""
        self.ensure_one()
        if month == int(self.month):
            return None
        records = self.search([("company_id", "=", self.company_id.id), ("year", "=", self.year),
            ("month", "=", str(month)), "|", ("filed_form_facts", "!=", False), ("submitted_attachment_id", "!=", False)])
        candidates = []
        for record in records:
            snapshot = record.filed_form_facts or record._prehlad_snapshot(record.submitted_attachment_id, legacy=True)
            snapshot = record._prehlad_check_snapshot(snapshot)
            review = snapshot.get("filing_order_review", snapshot.get("legacy_review", {}))
            candidates.append({
                "sequence": int(snapshot.get("local_filing_sequence", 0)),
                "order": int(review.get("order", 0)),
                "date": fields.Datetime.to_datetime(snapshot.get("submitted_on") or record.submitted_date),
                "snapshot": snapshot,
            })
        return self._prehlad_latest_filed_candidate(candidates)

    def _prehlad_latest_filed_candidate(self, candidates):
        """Select a proved latest filing, never treating an unknown order as first.

        A native sequence compares native filings only. A legacy import may
        have a later real timestamp. Written relative-order evidence resolves
        a tied/missing timestamp, including a mixed legacy/native tie. Earlier
        unresolved ties do not prevent selecting a provably later filing.
        """
        def comparison(left, right):
            native = left["sequence"] and right["sequence"]
            dated = left["date"] and right["date"] and left["date"] != right["date"]
            reviewed = left["order"] and right["order"]
            sequence_sign = (left["sequence"] > right["sequence"]) - (left["sequence"] < right["sequence"])
            date_sign = ((left["date"] > right["date"]) - (left["date"] < right["date"])) if dated else 0
            order_sign = (left["order"] > right["order"]) - (left["order"] < right["order"])
            if ((native and not sequence_sign)
                    or (reviewed and (not order_sign
                        or (native and sequence_sign != order_sign)
                        or (not native and dated and date_sign != order_sign)))):
                raise UserError(_("Review the conflicting relative order of the archived filings for this month."))
            if native:
                return sequence_sign
            if dated:
                return date_sign
            return order_sign if reviewed else 0

        # Validate known evidence even when a newer candidate exists. A
        # contradictory reviewed order must not silently disappear on reset.
        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                comparison(left, right)
        latest = [candidate for candidate in candidates if all(
            other is candidate or comparison(candidate, other) > 0
            for other in candidates)]
        if candidates and len(latest) != 1:
            raise UserError(_("Review the relative order of all indistinguishable archived filings for this month before using their quarterly facts."))
        return latest[0]["snapshot"] if latest else None

    def action_review_filing_order(self):
        """Qualify archive chronology, without recording a new authority filing."""
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            for record in self:
                snapshot = record._prehlad_check_snapshot(record.filed_form_facts) if record.filed_form_facts else None
                if snapshot is None:
                    raise UserError(_("Review the archived form facts before qualifying their filing order."))
                if record.legacy_filed_order <= 0 or not (record.legacy_filed_evidence or "").strip():
                    raise UserError(_("Record a positive relative filing order and the reviewed chronology evidence."))
                old = snapshot.get("filing_order_review", snapshot.get("legacy_review"))
                history = list(snapshot.get("filing_order_review_history", []))
                if old:
                    history.append(copy.deepcopy(old))
                snapshot["filing_order_review_history"] = history
                snapshot["filing_order_review"] = {
                    "order": record.legacy_filed_order, "evidence": record.legacy_filed_evidence,
                    "user": self.env.user.id, "on": str(fields.Datetime.now()),
                }
                super(PrehladFiledFacts, record).write({"filed_form_facts": snapshot})
        return True

    def _prehlad_quarter_component(self, month, component):
        snapshot = self._prehlad_quarter_retained(month)
        if snapshot is None:
            return None
        value = snapshot["quarter_components"].get(component)
        if value is None:
            raise UserError(_("Review the archived monthly premium facts before requesting their quarterly refund."))
        return value

    def _prehlad_quarter_proof(self, month):
        snapshot = self._prehlad_quarter_retained(month)
        return snapshot if snapshot is not None else self._prehlad_quarter_month(month)._prehlad_form_facts()

    def _prehlad_quarter_inputs(self, month):
        snapshot = self._prehlad_quarter_retained(month)
        if snapshot is None:
            return super()._prehlad_quarter_inputs(month)
        facts = snapshot["form_facts"]
        if facts.get("foreign_advance_amount") and not facts.get("foreign_advance_source"):
            raise UserError(_("Review the archived foreign advance classification."))
        return {name: (False if facts.get(name) == "False" else facts.get(name)) for name in (
            "foreign_advance_amount", "foreign_advance_source", "foreign_receipt_month",
            "prepared_on", "form_inputs_evidence")}

    def _prior_submitted(self):
        prior = super()._prior_submitted()
        if prior:
            return prior
        # A local reset does not cancel the actual archived original, including
        # when preparing its correction on the same document.
        return self.search([("company_id", "=", self.company_id.id),
            ("year", "=", self.year), ("month", "=", self.month),
            "|", ("filed_form_facts", "!=", False), ("submitted_attachment_id", "!=", False)])

    def action_review_legacy_filed_facts(self):
        with self.env.cr.savepoint():
            self._prehlad_lock_scope()
            for record in self:
                if record.filed_form_facts or not record.submitted_attachment_id:
                    raise UserError(_("Review legacy facts only for an existing archived filing without a facts snapshot."))
                if not (record.legacy_filed_evidence or "").strip():
                    raise UserError(_("Record the reviewed evidence for the archived filing."))
                snapshot = record._prehlad_snapshot(record.submitted_attachment_id, legacy=True)
                if snapshot["form_facts"]["foreign_advance_amount"] and not record.legacy_filed_foreign_source:
                    raise UserError(_("Review the archived foreign advance classification."))
                if not math.isfinite(record.legacy_filed_premium_own) or record.legacy_filed_premium_own < 0:
                    raise UserError(_("Use a finite nonnegative archived employee premium amount."))
                if record.legacy_filed_order < 0:
                    raise UserError(_("Use a nonnegative reviewed legacy filing order."))
                known_source = snapshot["form_facts"].get("foreign_advance_source")
                known_premium = snapshot["extension_source"].get("quarter_components", {}).get("premium")
                if ((known_source and known_source != record.legacy_filed_foreign_source)
                        or (known_premium is not None and known_premium != record.legacy_filed_premium_own)):
                    raise UserError(_("The reviewed archived facts must match their retained source proof."))
                snapshot["form_facts"]["foreign_advance_source"] = record.legacy_filed_foreign_source
                snapshot["quarter_components"]["premium"] = record.legacy_filed_premium_own
                snapshot["legacy_review"] = {"user": self.env.user.id, "on": str(fields.Datetime.now()),
                                             "evidence": record.legacy_filed_evidence,
                                             "order": record.legacy_filed_order}
                super(PrehladFiledFacts, record).write({"filed_form_facts": snapshot})
        return True
