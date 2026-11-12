# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Runtime test — proves Prehľad generation + XSD validation on BOTH payroll
engines. Detects whichever SK payroll engine is installed (the ``payroll`` engine
``l10n_sk_hr_payroll_oca`` or the ``l10n_sk_hr_payroll``), drives it to a
computed payslip, generates the monthly Prehľad and validates the produced XML
against the shipped ``prehlad2026.xsd``."""
import base64
import unittest
from datetime import date, datetime
from unittest.mock import patch

from lxml import etree
from odoo import fields

from odoo.exceptions import UserError, ValidationError
from odoo.addons.l10n_cssk_payroll_declaration_base.tests.common import (
    confirm_payslips,
)
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_path


@tagged("post_install", "-at_install")
class TestPrehlad(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls._detect_engine()
        if not cls.engine:
            raise unittest.SkipTest(
                "no SK payroll engine installed "
                "(l10n_sk_hr_payroll_oca or l10n_sk_hr_payroll)")
        cls.company = cls.env["res.company"].create({
            "name": "SK Prehlad Co s.r.o.",
            "country_id": cls.env.ref("base.sk").id,
            "company_registry": "12345679",
            "l10n_sk_dic": "1234567890",
            "street": "Hlavna 1",
            # A second address line, never the house number.
            "street2": "Budova B",
            "city": "Bratislava",
            "zip": "81101",
        })
        cls.env.user.company_ids |= cls.company
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=cls.company.ids))
        if cls.engine == "oca":
            cls.env.user.group_ids |= cls.env.ref(
                "payroll.group_payroll_manager")
            cls.structure = cls.env.ref(
                "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary")
        else:
            cls.env.user.group_ids |= cls.env.ref(
                "hr_payroll.group_hr_payroll_manager")
            cls.structure = cls.env.ref(
                "l10n_sk_hr_payroll.hr_payroll_structure_sk_employee_salary")
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "SK 40h", "company_id": cls.company.id})

    @classmethod
    def _detect_engine(cls):
        """Which SK payroll engine is installed, or None for neither.

        This used to test for the OCA engine and ASSUME the Enterprise one
        otherwise, then go on to ``env.ref`` an ``hr_payroll`` group. On a
        database with neither engine that raised in ``setUpClass``, so the whole
        suite errored instead of skipping -- and since a Community database
        without the OCA payroll engine is the common case, it had not run at
        all. That is how a fixture using a non-checksum-valid IČO survived
        unnoticed until 04da4a3.

        A missing engine is a skip, not a failure: there is no payslip to build
        a declaration from, and nothing in this module is under test without
        one.
        """
        if cls.env.ref(
                "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary",
                raise_if_not_found=False):
            return "oca"
        if cls.env.ref(
                "l10n_sk_hr_payroll.hr_payroll_structure_sk_employee_salary",
                raise_if_not_found=False):
            return "ee"
        return None

    def _employee_payslip(self, wage=2000.0):
        emp_vals = {
            "name": "Jozko Mrkvicka",
            "company_id": self.company.id,
            "resource_calendar_id": self.calendar.id,
            "identification_id": "8501011234",
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "wage": wage,
        }
        if self.engine == "oca":
            emp_vals["struct_id"] = self.structure.id
        else:
            emp_vals["structure_type_id"] = self.structure.type_id.id
        employee = self.env["hr.employee"].with_company(
            self.company).create(emp_vals)

        slip = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Payslip",
            "employee_id": employee.id,
            "struct_id": self.structure.id,
            "company_id": self.company.id,
            "date_from": date(2026, 3, 1),
            "date_to": date(2026, 3, 31),
        })
        if self.engine == "ee":
            slip = slip.with_context(salary_simulation=True)
        slip.compute_sheet()
        confirm_payslips(slip)
        return employee, slip

    def test_generate_and_validate(self):
        employee, slip = self._employee_payslip()
        totals = {line.code: line.total for line in slip.line_ids}
        split = abs(round(
            totals.get("INCOMETAX19", 0.0) + totals.get("INCOMETAX25", 0.0), 2))
        tax = split or abs(round(totals.get("INCOMETAX", 0.0), 2))
        self.assertGreater(tax, 0.0, "an income-tax advance must be computed")
        gross = abs(round(totals.get("GROSS", 0.0), 2))

        decl = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        })
        self.assertTrue(decl.version_id, "Prehľad version should default")
        decl.action_generate()
        self.assertEqual(decl.state, "generated")

        xml_bytes = base64.b64decode(decl.xml_attachment_id.datas)
        schema = etree.XMLSchema(etree.parse(
            file_path("l10n_sk_hr_payroll_monthly_tax_overview/data/prehlad2026.xsd")))
        root = etree.fromstring(xml_bytes)
        schema.assertValid(root)

        # root + header
        self.assertEqual(etree.QName(root).localname, "dokument")
        self.assertEqual(root.findtext("hlavicka/dic"), "1234567890")
        self.assertEqual(
            root.findtext("hlavicka/zdanovacieObdobie/mesiac"), "3")
        # sídlo: the house number split off the street, never Street 2
        self.assertEqual(root.findtext("hlavicka/sidlo/ulica"), "Hlavna")
        self.assertEqual(root.findtext("hlavicka/sidlo/cislo"), "1")

        # r00 = gross, r01/suma = withheld tax advance, r04 = r01
        self.assertAlmostEqual(
            float(root.findtext("telo/cast1/r00")), gross, 2)
        self.assertAlmostEqual(
            float(root.findtext("telo/cast1/r01/suma")), tax, 2)
        self.assertAlmostEqual(
            float(root.findtext("telo/cast1/r04")), tax, 2)
        # The wire uses signed reductions: r08 = r04 + r05 (no children).
        r05 = float(root.findtext("telo/cast1/r05"))
        r08 = float(root.findtext("telo/cast1/r08"))
        self.assertAlmostEqual(r08, round(tax + r05, 2), 2)

    def test_missing_dic_raises(self):
        self._employee_payslip()
        self.company.l10n_sk_dic = False
        decl = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        with self.assertRaises(UserError):
            decl.action_generate()

    # ------------------------------------------------------------------
    # Corrections (opravný Prehľad)
    # ------------------------------------------------------------------
    def _prehlad(self, **vals):
        base = {
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        }
        base.update(vals)
        return self.env["l10n.sk.prehlad"].with_company(self.company).create(base)

    def test_regular_prehlad_emits_riadny(self):
        """The default filing is riadny=1 / opravny=0."""
        self._employee_payslip()
        decl = self._prehlad()
        self.assertEqual(decl.correction_type, "regular")
        self.assertFalse(decl.is_correction)
        decl.action_generate()
        xml = base64.b64decode(decl.xml_attachment_id.datas).decode("utf-8")
        self.assertIn("<riadny>1</riadny>", xml)
        self.assertIn("<opravny>0</opravny>", xml)

    def test_corrective_prehlad_emits_opravny(self):
        """An opravný flips both flags. Before this the pair was hardcoded, so
        the form could only ever produce a regular Prehľad."""
        self._employee_payslip()
        first = self._prehlad()
        first.action_generate()
        first.action_submit()

        fix = self._prehlad(correction_type="corrective")
        self.assertTrue(fix.is_correction)
        with self.assertRaisesRegex(UserError, "actual discovery date"):
            fix.action_generate()
        fix.write({"correction_discovered_on": "2026-04-17", "prepared_on": "2026-04-20",
                   "form_inputs_evidence": "Synthetic reviewed discovery record"})
        fix.action_review_form_inputs()
        fix.action_generate()
        xml = base64.b64decode(fix.xml_attachment_id.datas).decode("utf-8")
        self.assertIn("<riadny>0</riadny>", xml)
        self.assertIn("<opravny>1</opravny>", xml)
        self.assertEqual(etree.fromstring(xml.encode()).findtext("hlavicka/datumZisteniaOP"), "17.04.2026")

    def test_discovery_boundaries_canonical_type_and_review(self):
        report = self._prehlad(correction_type="corrective", prepared_on="2026-04-20",
                               form_inputs_evidence="Synthetic review")
        for invalid in (False, "2026-02-28", "2026-04-21"):
            report.correction_discovered_on = invalid
            with self.assertRaises(UserError):
                report.action_review_form_inputs()
        for valid in ("2026-03-01", "2026-04-20"):
            report.correction_discovered_on = valid
            report.action_review_form_inputs()
            report._prehlad_validate_form_facts()
        report.write({"is_correction": False})
        self.assertTrue(report._is_amending_declaration())
        report.correction_type = "regular"
        with self.assertRaisesRegex(UserError, "regular overview"):
            report.action_review_form_inputs()
        report.correction_discovered_on = False
        report.action_review_form_inputs()

    def test_form_review_api_defaults_and_stale_evidence(self):
        for field in ("form_inputs_reviewed_by", "form_inputs_reviewed_at", "form_inputs_digest"):
            with self.assertRaises(UserError):
                self._prehlad(**{field: False})
            with self.assertRaises(UserError):
                self.env["l10n.sk.prehlad"].with_company(self.company).with_context(
                    **{"default_" + field: False}).create({"year": "2026", "month": "3"})
        report = self._prehlad(prior_advance_offset=True, form_inputs_evidence="Synthetic prior excess remittance")
        with self.assertRaisesRegex(UserError, "Review the current"):
            report._prehlad_validate_form_facts()
        report.action_review_form_inputs()
        report._prehlad_validate_form_facts()
        report.form_inputs_evidence = "Changed source"
        self.assertFalse(report.form_inputs_reviewed_by)
        with self.assertRaises(UserError):
            report._prehlad_validate_form_facts()

    def test_foreign_classification_external_fact_and_row8b(self):
        self._employee_payslip()
        report = self._prehlad(prepared_on="2026-04-20", foreign_receipt_month="2026-04-01",
            foreign_advance_amount=20, foreign_advance_source="included", prior_advance_offset=True,
            form_inputs_evidence="Synthetic foreign income document and earlier excess advance offset")
        report.action_review_form_inputs()
        report.action_generate()
        original = base64.b64decode(report.xml_attachment_id.datas)
        root = etree.fromstring(original)
        native = report._tax_advance(report._collect_payslip_totals(report._get_period_payslips())["aggregate"])
        self.assertAlmostEqual(float(root.findtext("telo/cast1/r01/suma")), native - 20, 2)
        self.assertEqual(root.findtext("telo/cast1/r01a/mesiacRok"), "04.2026")
        self.assertEqual(float(root.findtext("telo/cast1/r01a/suma")), 20)
        self.assertEqual(root.findtext("telo/cast1/r08b"), "1")
        self.assertAlmostEqual(float(root.findtext("telo/cast1/r04")), native, 2)
        self.assertFalse(root.findtext("telo/cast1/r01b"))
        with self.assertRaises(UserError):
            report.write({"prior_advance_offset": False})
        report.action_submit()
        filed = report.submitted_attachment_id
        duplicate = report.copy()
        self.assertEqual(duplicate.state, "draft")
        self.assertFalse(duplicate.xml_attachment_id)
        self.assertFalse(duplicate.foreign_receipt_month)
        self.assertFalse(duplicate.form_inputs_reviewed_by)
        report.action_reset_to_draft()
        self.assertFalse(report.form_inputs_reviewed_by)
        report.write({"foreign_advance_source": "additional", "prior_advance_offset": False})
        report.action_review_form_inputs()
        report.action_generate()
        revised = etree.fromstring(base64.b64decode(report.xml_attachment_id.datas))
        self.assertAlmostEqual(float(revised.findtext("telo/cast1/r04")), native + 20, 2)
        self.assertEqual(revised.findtext("telo/cast1/r08b"), "0")
        self.assertEqual(base64.b64decode(filed.datas), original)

    def test_conditional_fact_negative_inputs(self):
        report = self._prehlad(prepared_on="2026-04-20", foreign_advance_amount=20,
                               form_inputs_evidence="Synthetic foreign income document")
        with self.assertRaises(UserError):
            report.action_review_form_inputs()
        report.write({"foreign_receipt_month": "2026-04-02", "foreign_advance_source": "additional"})
        with self.assertRaises(UserError):
            report.action_review_form_inputs()
        report.foreign_receipt_month = "2026-05-01"
        with self.assertRaises(UserError):
            report.action_review_form_inputs()
        report.foreign_receipt_month = "2026-03-01"
        with self.assertRaisesRegex(UserError, "following the reporting month"):
            report.action_review_form_inputs()
        report.write({"foreign_receipt_month": "2026-04-01", "foreign_advance_amount": -1})
        with self.assertRaises(UserError):
            report.action_review_form_inputs()
        report.foreign_advance_amount = 20
        report.foreign_advance_source = "included"
        with self.assertRaisesRegex(UserError, "exceeds"):
            report._prehlad_advance_rows(10)

    def test_quarter_refund_reuses_reviewed_monthly_foreign_capacity_once(self):
        difference = self._bonus_quarter()
        january = self._prehlad(month="1", prepared_on="2026-02-20",
            foreign_receipt_month="2026-02-01", foreign_advance_amount=20,
            foreign_advance_source="additional", form_inputs_evidence="Synthetic January foreign income document")
        january.action_review_form_inputs()
        january.action_generate()
        january.action_submit()
        march = self._prehlad()
        self.assertAlmostEqual(march._quarter_bonus_difference(), difference - 20, 2)
        # A later unfiled draft is not a replacement for the completed month.
        self._prehlad(month="1", foreign_advance_amount=90)
        self.assertAlmostEqual(march._quarter_bonus_difference(), difference - 20, 2)

    def test_reset_filed_month_keeps_quarter_capacity(self):
        baseline = self._bonus_quarter()
        january = self._prehlad(month='1', prepared_on='2026-02-20',
            foreign_receipt_month='2026-02-01', foreign_advance_amount=20,
            foreign_advance_source='additional', form_inputs_evidence='Reviewed foreign advance 20')
        january.action_review_form_inputs()
        january.action_generate()
        january.action_submit()
        archived = january.submitted_attachment_id
        original = base64.b64decode(archived.datas)
        march = self._prehlad(request_bonus_refund=True)
        march.action_generate()
        before = float(self._cast3(march).findtext('suma'))
        self.assertAlmostEqual(before, baseline - 20, 2)
        march.action_reset_to_draft()
        january.action_reset_to_draft()
        # Reset is a local preparation action, not a cancellation at FS.
        self.assertEqual(base64.b64decode(archived.datas), original)
        self.assertEqual(january.state, 'draft')
        march.action_generate()
        after = float(self._cast3(march).findtext('suma'))
        self.assertAlmostEqual(after, before, 2,
            'Merely resetting a filed January increased the actual quarterly refund XML')

    def test_internal_quarter_months_ignore_creation_defaults(self):
        baseline = self._bonus_quarter()
        march = self._prehlad(request_bonus_refund=True).with_context(
            default_foreign_advance_amount=-20,
            default_foreign_advance_source="additional")
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline, 2,
            "UI creation defaults are not reviewed facts for earlier virtual months")

    def test_repeat_filing_order_does_not_follow_document_id(self):
        baseline = self._bonus_quarter()
        original = self._prehlad(month="1")
        original.action_generate()
        original.action_submit()
        first = self._prehlad(month="1", correction_type="corrective",
            correction_discovered_on="2026-02-17", prepared_on="2026-02-20",
            foreign_receipt_month="2026-02-01", foreign_advance_amount=30,
            foreign_advance_source="additional", form_inputs_evidence="Synthetic earlier document filed later")
        second = self._prehlad(month="1", correction_type="corrective",
            correction_discovered_on="2026-02-17", prepared_on="2026-02-20",
            foreign_receipt_month="2026-02-01", foreign_advance_amount=40,
            foreign_advance_source="additional", form_inputs_evidence="Synthetic later document filed first")
        first.action_review_form_inputs()
        second.action_review_form_inputs()
        first.action_generate()
        second.action_generate()
        with patch.object(fields.Datetime, "now", return_value=datetime(2028, 2, 20, 12, 0)):
            second.action_submit()
            first.action_submit()
        self.assertEqual(first.submitted_date, second.submitted_date)
        self.assertLess(first.id, second.id)
        march = self._prehlad(request_bonus_refund=True)
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline - 30, 2)

    def test_filed_facts_survive_edit_generated_and_effective_correction(self):
        baseline = self._bonus_quarter()
        january = self._prehlad(month="1", prepared_on="2026-02-20",
            foreign_receipt_month="2026-02-01", foreign_advance_amount=20,
            foreign_advance_source="additional", prior_advance_offset=True,
            form_inputs_evidence="Synthetic first filed foreign advance")
        january.action_review_form_inputs()
        january.action_generate()
        january.action_submit()
        archived = january.submitted_attachment_id
        original = base64.b64decode(archived.datas)
        sequence = january.filed_form_facts["local_filing_sequence"]
        march = self._prehlad(request_bonus_refund=True)
        january.action_reset_to_draft()
        january.write({"correction_type": "corrective", "correction_discovered_on": "2026-02-18",
            "foreign_advance_amount": 40, "prior_advance_offset": False,
            "form_inputs_evidence": "Synthetic reviewed correction, not yet filed"})
        january.action_review_form_inputs()
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline - 20, 2)
        january.action_generate()
        self.assertEqual(january.generated_form_facts["form_facts"]["foreign_advance_amount"], 40)
        self.assertEqual(january.filed_form_facts["form_facts"]["foreign_advance_amount"], 20)
        self.assertTrue(january.filed_form_facts["form_facts"]["prior_advance_offset"])
        march.action_reset_to_draft()
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline - 20, 2)
        january.action_submit()
        self.assertGreater(january.filed_form_facts["local_filing_sequence"], sequence)
        self.assertEqual(january.filed_form_facts["form_facts"]["correction_discovered_on"], "2026-02-18")
        history = january.filed_form_facts.get("previous_filed_facts", [])
        self.assertEqual(len(history), 1, "The earlier filed form classification/source evidence must remain archived")
        self.assertEqual(history[0]["attachment_id"], archived.id)
        self.assertEqual(history[0]["form_facts"]["foreign_advance_amount"], 20)
        self.assertEqual(history[0]["form_facts"]["foreign_advance_source"], "additional")
        march.action_reset_to_draft()
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline - 40, 2)
        self.assertEqual(base64.b64decode(archived.datas), original)
        duplicate = january.copy()
        self.assertFalse(duplicate.filed_form_facts)
        self.assertFalse(duplicate.generated_form_facts)
        duplicate.unlink()
        self.assertFalse(duplicate.exists())
        for name in ("filed_form_facts", "generated_form_facts"):
            with self.assertRaises(UserError):
                january.write({name: False})
            with self.assertRaises(UserError):
                self._prehlad(**{name: False})
            with self.assertRaises(UserError):
                self.env["l10n.sk.prehlad"].with_company(self.company).with_context(
                    **{"default_" + name: False}).create({"year": "2026", "month": "1"})
        january.action_reset_to_draft()
        with self.assertRaises(UserError):
            january.unlink()
        with self.assertRaises(UserError):
            january.month = "2"

    def test_filing_facts_failure_rolls_back_native_submission(self):
        self._employee_payslip()
        report = self._prehlad()
        report.action_generate()
        with patch.object(type(report), "_prehlad_next_filing_sequence", side_effect=UserError("Synthetic snapshot failure")):
            with self.assertRaisesRegex(UserError, "Synthetic snapshot failure"):
                report.action_submit()
        self.assertEqual(report.state, "generated")
        self.assertFalse(report.submitted_attachment_id)
        self.assertFalse(report.filed_form_facts)
        self.assertFalse(report.filed_history_ids)
        report.action_submit()
        self.assertEqual(report.state, "submitted")
        self.assertEqual(report.filed_form_facts["attachment_id"], report.submitted_attachment_id.id)

    def test_api_cannot_invent_a_filed_pointer_or_filing_state(self):
        self._employee_payslip()
        report = self._prehlad()
        report.action_generate()
        with self.assertRaises(UserError):
            report.write({"submitted_attachment_id": report.xml_attachment_id.id})
        with self.assertRaises(UserError):
            report.write({"state": "submitted"})
        with self.assertRaises(UserError):
            self._prehlad(submitted_attachment_id=False)
        with self.assertRaises(UserError):
            self.env["l10n.sk.prehlad"].with_company(self.company).with_context(
                default_submitted_attachment_id=False).create({"year": "2026", "month": "3"})

    def test_legacy_quarter_uses_archived_xml_and_reviewed_classification(self):
        baseline = self._bonus_quarter()
        january = self._prehlad(month="1", prepared_on="2026-02-20",
            foreign_receipt_month="2026-02-01", foreign_advance_amount=20,
            foreign_advance_source="additional", form_inputs_evidence="Synthetic legacy original")
        january.action_review_form_inputs()
        january.action_generate()
        january.action_submit()
        # Import fixture for a pre-upgrade filed record without the new field.
        self.env.cr.execute("UPDATE l10n_sk_prehlad SET filed_form_facts = NULL WHERE id = %s", [january.id])
        january.invalidate_recordset()
        january.action_reset_to_draft()
        january.foreign_advance_amount = 99
        march = self._prehlad(request_bonus_refund=True)
        march.action_generate()
        self.assertAlmostEqual(float(self._cast3(march).findtext("suma")), baseline - 20, 2)
        with self.assertRaises(UserError):
            march._prehlad_quarter_inputs(1)
        january.write({"legacy_filed_evidence": "Synthetic review of the archived foreign income document",
                       "legacy_filed_foreign_source": "additional"})
        january.action_review_legacy_filed_facts()
        facts = march._prehlad_quarter_inputs(1)
        self.assertEqual(facts["foreign_advance_amount"], 20)
        self.assertEqual(facts["foreign_advance_source"], "additional")
        self.assertEqual(january.filed_form_facts["local_filing_sequence"], 0)

    def test_correction_needs_something_to_correct(self):
        """An opravný for a period never filed is a rejection at best and a
        duplicate at worst, so generating one is refused."""
        # Seed a payslip: without one the generation would be refused for
        # having nothing to report, and the test would pass whether or not the
        # correction guard exists.
        self._employee_payslip()
        fix = self._prehlad(correction_type="corrective")
        with self.assertRaises(UserError):
            fix.action_generate()

    def test_a_draft_original_does_not_count_as_filed(self):
        """Only a SUBMITTED filing can be amended — a draft or generated one
        has not reached the Finančná správa."""
        self._employee_payslip()
        first = self._prehlad()
        first.action_generate()          # generated, not submitted
        fix = self._prehlad(correction_type="corrective")
        with self.assertRaises(UserError):
            fix.action_generate()

    def test_unsupported_correction_types_are_refused(self):
        """The FS Prehľad wire format has no dodatočný and no storno, so the
        selection must not offer them."""
        offered = dict(
            self.env["l10n.sk.prehlad"]
            .fields_get(["correction_type"])["correction_type"]["selection"]
        )
        self.assertEqual(set(offered), {"regular", "corrective"})
        # A dynamic selection cannot be validated by the ORM the way a literal
        # one is, so the constraint is what actually stops it — which is the
        # reason the constraint exists rather than relying on the field.
        with self.assertRaises(ValidationError):
            self._prehlad(correction_type="storno")

    def test_legal_form_comes_from_the_register_field(self):
        """pravnaForma carries the partner's recorded právna forma.

        The model called a ``company.l10n_sk_legal_form()`` method that no
        module defines, behind a ``hasattr`` that was therefore always False,
        so the element was always empty.
        """
        partner = self.company.partner_id
        if "l10n_sk_legal_form" not in partner._fields:
            self.skipTest("l10n_sk_trade_registry is not installed")
        partner.l10n_sk_legal_form = "spoločnosť s ručením obmedzeným"
        self._employee_payslip()
        decl = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        })
        decl.action_generate()
        root = etree.fromstring(base64.b64decode(decl.xml_attachment_id.datas))
        self.assertEqual(root.findtext("hlavicka/po/pravnaForma"),
                         "spoločnosť s ručením obmedzeným")

    # ------------------------------------------------------------------
    # III. časť — žiadosť o poukázanie rozdielu daňového bonusu (2026-10-27)
    # ------------------------------------------------------------------
    def _bonus_quarter(self):
        """A low wage with four children: in each month of Q1 2026 the § 33
        bonus exceeds the withheld advance. Returns Σ r. C of the quarter."""
        emp_vals = {
            "name": "Bonus Velky",
            "company_id": self.company.id,
            "resource_calendar_id": self.calendar.id,
            "identification_id": "8501011234",
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "wage": 915.0,
        }
        if self.engine == "oca":
            emp_vals["struct_id"] = self.structure.id
        else:
            emp_vals["structure_type_id"] = self.structure.type_id.id
        employee = self.env["hr.employee"].with_company(
            self.company).create(emp_vals)
        employee.version_id.write({
            "l10n_sk_tax_declaration_signed": True,
            "l10n_sk_children_under_15": 4,
        })
        expected = 0.0
        for month, last in ((1, 31), (2, 28), (3, 31)):
            slip = self.env["hr.payslip"].with_company(self.company).create({
                "name": "Payslip %d" % month,
                "employee_id": employee.id,
                "struct_id": self.structure.id,
                "company_id": self.company.id,
                "date_from": date(2026, month, 1),
                "date_to": date(2026, month, last),
            })
            if self.engine == "ee":
                slip = slip.with_context(salary_simulation=True)
            slip.compute_sheet()
            confirm_payslips(slip)
            totals = {}
            for line in slip.line_ids:
                totals[line.code] = totals.get(line.code, 0.0) + line.total
            advance = abs(round(
                totals.get("INCOMETAX19", 0.0)
                + totals.get("INCOMETAX25", 0.0), 2)) or abs(
                round(totals.get("INCOMETAX", 0.0), 2))
            bonus = abs(round(totals.get("CHILD_BONUS", 0.0), 2))
            self.assertGreater(bonus, advance, "premise: bonus > advance")
            expected += bonus - min(bonus, advance)
        self.company.partner_id.bank_ids = [(0, 0, {
            "acc_number": "SK3112000000198742637541"})]
        return round(expected, 2)

    def _cast3(self, decl):
        root = etree.fromstring(base64.b64decode(decl.xml_attachment_id.datas))
        etree.XMLSchema(etree.parse(file_path(
            "l10n_sk_hr_payroll_monthly_tax_overview/data/prehlad2026.xsd"))
        ).assertValid(root)
        return root.find("telo/cast3/poukazatBonus")

    def test_computed_paid_bonus_uses_signed_wire_and_positive_recap(self):
        self._bonus_quarter()
        report = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        report.action_generate()
        root = etree.fromstring(base64.b64decode(report.xml_attachment_id.datas))
        paid = float(root.findtext("telo/cast1/r05"))
        self.assertLess(paid, 0)
        self.assertEqual(float(root.findtext("telo/cast1/r08")),
                         float(root.findtext("telo/cast1/r04")) + paid)
        self.assertEqual(float(root.findtext("telo/cast2/rB")), -paid)

    def test_bonus_difference_refund_is_claimed_for_the_quarter(self):
        """The bonus paid beyond the advances (r. C) was reported but could
        never be claimed: III. časť was hardcoded to ziadam=0."""
        expected = self._bonus_quarter()
        self.assertGreater(expected, 0.0)
        decl = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3",
            "request_bonus_refund": True,
        })
        decl.action_generate()
        node = self._cast3(decl)
        self.assertEqual(node.findtext("ziadam"), "1")
        self.assertAlmostEqual(float(node.findtext("suma")), expected, 2)

    def test_bonus_difference_refund_is_opt_in(self):
        self._bonus_quarter()
        decl = self.env["l10n.sk.prehlad"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        decl.action_generate()
        node = self._cast3(decl)
        self.assertEqual(node.findtext("ziadam"), "0")
        self.assertFalse((node.findtext("suma") or "").strip())

    def test_bonus_difference_refund_only_at_quarter_end(self):
        """The poučenie: no žiadosť in the overviews for January and
        February — only after the quarter ends."""
        with self.assertRaises(ValidationError):
            self.env["l10n.sk.prehlad"].with_company(self.company).create({
                "company_id": self.company.id, "year": "2026", "month": "2",
                "request_bonus_refund": True,
            })


@tagged("post_install", "-at_install")
class TestSchemaPins(TransactionCase):
    """The bundled schemas must match data/SCHEMA_VERSION.

    Not a check that our copies are CURRENT — nothing local can answer that,
    and a schema revised in place by the authority validates exactly as
    before. What this checks is that the bundled bytes are the ones recorded
    in SCHEMA_VERSION, and that no schema sits in data/ unpinned.
    """

    @staticmethod
    def _data_dir():
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "data")

    def _pins(self):
        import os
        pins = {}
        path = os.path.join(self._data_dir(), "SCHEMA_VERSION")
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                parts = raw.split()
                if (len(parts) == 3 and parts[0].endswith(".xsd")
                        and "/" not in parts[0]):
                    pins[parts[0]] = (parts[1], int(parts[2]))
        return pins

    def test_bundled_schemas_match_the_pinned_digests(self):
        import hashlib
        import os
        pins = self._pins()
        self.assertTrue(pins, "SCHEMA_VERSION lists no schemas")
        for name, (digest, size) in pins.items():
            path = os.path.join(self._data_dir(), name)
            self.assertTrue(os.path.exists(path),
                            "%s is pinned but missing" % name)
            with open(path, "rb") as fh:
                blob = fh.read()
            self.assertEqual(len(blob), size, "%s size moved" % name)
            self.assertEqual(
                hashlib.md5(blob).hexdigest(), digest,
                "%s does not match its pin — if this is a deliberate "
                "refresh, update data/SCHEMA_VERSION" % name)

    def test_every_bundled_schema_is_pinned(self):
        import os
        on_disk = {f for f in os.listdir(self._data_dir())
                   if f.endswith(".xsd")}
        self.assertEqual(on_disk, set(self._pins()),
                         "unpinned schema(s): %s"
                         % sorted(on_disk - set(self._pins())))
