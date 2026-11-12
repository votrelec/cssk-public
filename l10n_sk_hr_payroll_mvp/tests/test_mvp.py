# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Runtime test — proves MVP generation + XSD validation on BOTH payroll
engines. Detects whichever SK payroll engine is installed (the ``payroll`` engine
``l10n_sk_hr_payroll_oca`` or the ``l10n_sk_hr_payroll``), drives it to a
computed payslip, generates the MVP declaration and validates the produced XML
against the shipped ``MVPP-v2026.xsd``."""
import base64
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_DOWN
import json
from unittest.mock import patch

from lxml import etree

from odoo.addons.l10n_cssk_payroll_declaration_base.tests.common import (
    confirm_payslips,
)
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError
from odoo.tools import file_path

NS = {"m": "http://socpoist.sk/xsd/mvpp2026"}


@tagged("post_install", "-at_install")
class MvpCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.engine = cls._detect_engine()
        cls.company = cls.env["res.company"].create({
            "name": "SK MVP Co",
            "country_id": cls.env.ref("base.sk").id,
            "company_registry": "12345679",
            "l10n_sk_sp_vs": "1234567890",
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
        if cls.env.ref(
                "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary",
                raise_if_not_found=False):
            return "oca"
        return "ee"

    def _employee_payslip(self, wage=2000.0, agreement="none", regular=None,
                          identification="8501011234", period=None):
        emp_vals = {
            "name": "Jozko Mrkvicka",
            "company_id": self.company.id,
            "resource_calendar_id": self.calendar.id,
            "identification_id": identification,  # rodné číslo
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "wage": wage,
        }
        # A dohoda sits on its own structure (OCA) or structure type
        # (Enterprise): the structure decides the employment form.
        structure = self.structure
        if self.engine == "oca":
            if agreement != "none":
                structure = self.env.ref(
                    "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_%s"
                    % agreement)
            emp_vals["struct_id"] = structure.id
        else:
            structure_type = self.structure.type_id
            if agreement != "none":
                structure_type = self.env.ref(
                    "l10n_sk_hr_payroll_ee.structure_type_%s_sk" % agreement)
                structure = structure_type.default_struct_id
            emp_vals["structure_type_id"] = structure_type.id
        employee = self.env["hr.employee"].with_company(
            self.company).create(emp_vals)
        self.assertEqual(employee.version_id.l10n_sk_agreement_type, agreement)
        if regular is not None:
            employee.version_id.l10n_sk_income_regular = regular

        slip = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Payslip",
            "employee_id": employee.id,
            "struct_id": structure.id,
            "company_id": self.company.id,
            "date_from": period[0] if period else date(2026, 3, 1),
            "date_to": period[1] if period else date(2026, 3, 31),
        })
        if self.engine == "ee":
            slip = slip.with_context(salary_simulation=True)
        slip.compute_sheet()
        confirm_payslips(slip)
        return employee, slip


class TestMvp(MvpCase):
    def test_generate_and_validate(self):
        employee, slip = self._employee_payslip()
        totals = {line.code: line.total for line in slip.line_ids}
        social_er = abs(round(totals.get("SOCIALEMPLOYERTOTAL", 0.0), 2))
        social_ee = abs(round(totals.get("SOCIALEMPLOYEETOTAL", 0.0), 2))
        self.assertGreater(social_er, 0.0, "employer social must be computed")

        decl = self.env["l10n.sk.mvp"].with_company(self.company).create({
            "company_id": self.company.id,
            "year": "2026",
            "month": "3",
            "payment_date": date(2026, 3, 31),
        })
        self.assertTrue(decl.version_id, "MVP version should default")
        decl.action_generate()
        self.assertEqual(decl.state, "generated")

        xml_bytes = base64.b64decode(decl.xml_attachment_id.datas)
        schema = etree.XMLSchema(etree.parse(
            file_path("l10n_sk_hr_payroll_mvp/data/MVPP-v2026.xsd")))
        root = etree.fromstring(xml_bytes)
        schema.assertValid(root)

        # Aggregate total matches the payslip.
        # spoluPoistne must equal the sum of the fund rows this form reports,
        # and NOTHING else. It used to be asserted against the payslip's
        # SOCIALEMPLOYERTOTAL + SOCIALEMPLOYEETOTAL categories — but those
        # carry the HEALTH premiums as well (HEALTH and HEALTHDOPLATOK sit in
        # SOCIALEMPLOYEE, HEALTHEMPLOYER in SOCIALEMPLOYER), which are owed to
        # the health insurers and reported on dávka 514. Asserting against the
        # categories made this test ratify an over-stated social premium and
        # an internally inconsistent form.
        poistne = root.find(".//m:poistne", NS)
        rows = sum(
            float(el.text)
            for el in poistne.iter()
            if etree.QName(el).localname.endswith(("Zamtel", "Zamnec"))
            and el.text
        )
        spolu = float(root.find(".//m:poistne/m:spoluPoistne", NS).text)
        self.assertAlmostEqual(
            spolu, round(rows, 2), 2,
            "spoluPoistne must be the sum of the fund rows")
        # ...and it must exclude health, i.e. fall short of the payslip's
        # health-contaminated social categories by exactly the health premium.
        health = abs(round(totals.get("HEALTH", 0.0), 2)) + abs(
            round(totals.get("HEALTHEMPLOYER", 0.0), 2))
        self.assertAlmostEqual(
            spolu, round(social_er + social_ee - health, 2), 2,
            "the social premium must exclude health insurance")

        # Per-employee annex present with the employee's rodné číslo.
        annex = root.findall(".//m:poistneZamestnanca", NS)
        self.assertEqual(len(annex), 1)
        self.assertEqual(annex[0].get("rc"), "8501011234")

    def test_missing_rc_raises(self):
        from odoo.exceptions import UserError
        employee, slip = self._employee_payslip()
        employee.identification_id = False
        decl = self.env["l10n.sk.mvp"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        with self.assertRaises(UserError):
            decl.action_generate()

    def _mvp(self):
        return self.env["l10n.sk.mvp"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})

    def test_original_automatically_warns_for_missing_funds_without_changing_xml(self):
        _employee, slip = self._employee_payslip()
        reference = self._mvp()
        reference.action_generate()
        previous = base64.b64decode(reference.xml_attachment_id.datas)
        original = self._mvp()
        with patch.object(type(slip), "_cssk_recorded_fund_bases", return_value=False, create=True):
            original.action_generate()
        self.assertIn(slip.display_name, original.fund_bases_warning)
        self.assertEqual(base64.b64decode(original.xml_attachment_id.datas), previous)

    def test_original_automatically_warns_for_inconsistent_stored_funds(self):
        if self.engine != "oca":
            self.skipTest("OCA owns this record writer")
        _employee, slip = self._employee_payslip()
        # Model historical database drift without bypassing today's public
        # source guards through a normal salary-line write.
        evidence = deepcopy(slip.l10n_sk_fund_assessment)
        evidence["identity"]["date_to"] = "2026-04-30"
        self.env.cr.execute("UPDATE hr_payslip SET l10n_sk_fund_assessment=%s::jsonb WHERE id=%s", [json.dumps(evidence), slip.id])
        slip.invalidate_recordset(["l10n_sk_fund_assessment"])
        original = self._mvp()
        original.action_generate()
        self.assertIn(slip.display_name, original.fund_bases_warning)

    def test_dohody_follow_income_regularity(self):
        """A dohoda with regular income is reported here, under its own
        relationship code; one with irregular income goes to the VPP and
        must not be reported here as well (cssk-public#12)."""
        _e1, regular = self._employee_payslip(
            wage=1000.0, agreement="dopc", regular=True)
        _e2, irregular = self._employee_payslip(
            wage=1000.0, agreement="dovp", regular=False,
            identification="9001011236")
        decl = self._mvp()
        self.assertEqual(decl._get_period_payslips(), regular)
        self.assertNotIn(irregular, decl._get_period_payslips())
        decl.action_generate()
        root = etree.fromstring(base64.b64decode(decl.xml_attachment_id.datas))
        etree.XMLSchema(etree.parse(file_path(
            "l10n_sk_hr_payroll_mvp/data/MVPP-v2026.xsd"))).assertValid(root)
        codes = {row.get("rc"): row.get("typZec")
                 for row in root.findall(".//m:poistneZamestnanca", NS)}
        self.assertEqual(codes, {"8501011234": "ZECD2"})

    def test_later_contract_change_keeps_the_past_period(self):
        """The payslip's own contract version decides, not today's: a DoPČ
        irregular in March and re-agreed as regular from April stays off the
        March MVP."""
        employee, slip = self._employee_payslip(
            wage=1000.0, agreement="dopc", regular=False)
        march = employee.version_id
        employee.create_version({
            "date_version": date(2026, 4, 1),
            "l10n_sk_income_regular": True,
        })
        self.assertNotEqual(employee.version_id, march)
        self.assertTrue(employee.version_id.l10n_sk_income_regular)
        self.assertNotIn(slip, self._mvp()._get_period_payslips())

    def test_sp_vs_is_editable_on_the_form(self):
        """The variable symbol is required by the preflight but was on no
        form at all; it is edited on the declaration form now."""
        arch = self.env["l10n.sk.mvp"].get_views(
            [(False, "form")])["views"]["form"]["arch"]
        self.assertIn('name="sp_vs"', arch)
        decl = self.env["l10n.sk.mvp"].with_company(self.company).create({
            "company_id": self.company.id, "year": "2026", "month": "3"})
        decl.sp_vs = "9988776655"
        self.assertEqual(self.company.l10n_sk_sp_vs, "9988776655")

    def _assert_recorded_wire_bases(self, declaration, slips):
        from ..models.l10n_sk_mvp import FUND_BASE_MAP
        declaration.action_generate()
        tree = etree.fromstring(base64.b64decode(declaration.xml_attachment_id.datas))
        row = tree.find(".//m:poistneZamestnanca", NS)
        expected = {field: Decimal(0) for field, _code in FUND_BASE_MAP.values()}
        for slip in slips:
            for record in slip._cssk_recorded_fund_bases():
                key = record["fund"], record["side"]
                if key in FUND_BASE_MAP:
                    expected[FUND_BASE_MAP[key][0]] += Decimal(record["base"])
        for field, value in expected.items():
            self.assertEqual(Decimal(row.get(field)), abs(value).quantize(Decimal(".01"), rounding=ROUND_DOWN), field)
        return declaration, row

    def test_recorded_fund_bases_reach_every_annex_field(self):
        if self.engine != "oca":
            self.skipTest("Recorded OCA source fixture")
        employee, slip = self._employee_payslip(20000)
        _declaration, row = self._assert_recorded_wire_bases(self._mvp(), slip)
        self.assertEqual(row.get("vzNp"), "16764.00")
        self.assertEqual(row.get("vzUp"), "20000.00")
        employee.create_version({"date_version": date(2026, 4, 1), "wage": 100})
        self._assert_recorded_wire_bases(self._mvp(), slip)

    def test_native_refund_replacement_uses_only_effective_sources(self):
        if self.engine != "oca":
            self.skipTest("Native OCA refund linkage")
        _employee, original = self._employee_payslip(20000)
        frozen = deepcopy(original.l10n_sk_fund_assessment)
        original.refund_sheet()
        replacement = original.copy({"name": "Replacement original remuneration"})
        replacement.compute_sheet()
        confirm_payslips(replacement)
        declaration = self._mvp()
        self.assertEqual(declaration._get_period_payslips(), replacement)
        self._assert_recorded_wire_bases(declaration, replacement)
        self.assertEqual(original.l10n_sk_fund_assessment, frozen)

    def test_partial_month_preserves_distinct_employee_and_employer_caps(self):
        if self.engine != "oca":
            self.skipTest("Recorded OCA source fixture")
        employee = self.env["hr.employee"].with_company(self.company).create({
            "name": "Mid-month high income", "company_id": self.company.id,
            "identification_id": "8501011234", "struct_id": self.structure.id,
            "date_version": date(2026, 3, 15), "contract_date_start": date(2026, 3, 15),
            "wage": 60000, "resource_calendar_id": self.calendar.id,
        })
        slip = self.env["hr.payslip"].with_company(self.company).create({
            "name": "Partial month native source", "company_id": self.company.id,
            "employee_id": employee.id, "contract_id": employee.version_id.id,
            "struct_id": self.structure.id, "date_from": date(2026, 3, 1), "date_to": date(2026, 3, 31),
        })
        slip.compute_sheet()
        confirm_payslips(slip)
        _declaration, row = self._assert_recorded_wire_bases(self._mvp(), slip)
        self.assertEqual(row.get("vzNp"), "16764.00")
        daily = (Decimal("16764") / 31).quantize(Decimal(".01"), rounding=ROUND_DOWN)
        self.assertEqual(Decimal(row.get("vzZecNp")), daily * 17)
        self.assertGreater(Decimal(row.get("vzUp")), Decimal("16764"))

    def test_agreement_oop_once_and_noninsured_funds_are_zero(self):
        if self.engine != "oca":
            self.skipTest("Recorded OCA agreement fixture")
        structure = self.env.ref("l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_dopc")
        rule = self.env["hr.salary.rule"].create({
            "name": "Synthetic additional agreement remuneration", "code": "MVP_TEST_GROSS",
            "sequence": 90, "category_id": self.env.ref("l10n_sk_hr_payroll_oca.ALW").id,
            "condition_select": "none", "amount_select": "code", "amount_python_compute": "result = 200",
        })
        structure.rule_ids |= rule
        employee = self.env["hr.employee"].with_company(self.company).create({
            "name": "Regular old-age agreement", "company_id": self.company.id,
            "identification_id": "8501011234", "struct_id": structure.id,
            "date_version": date(2026, 1, 1), "contract_date_start": date(2026, 1, 1),
            "wage": 0, "l10n_sk_hourly_wage": 0, "l10n_sk_agreement_oop": True,
            "l10n_sk_pension_type": "old_age", "l10n_sk_income_regular": True,
        })
        values = {"name": "Synthetic actual remuneration", "company_id": self.company.id,
                  "employee_id": employee.id, "contract_id": employee.version_id.id,
                  "struct_id": structure.id, "date_from": date(2026, 3, 1), "date_to": date(2026, 3, 31)}
        slips = self.env["hr.payslip"].with_company(self.company).create([values, dict(values)])
        slips.action_payslip_done()
        _declaration, row = self._assert_recorded_wire_bases(self._mvp(), slips)
        self.assertEqual(row.get("vzSp"), "200.00")
        self.assertEqual(row.get("vzZecSp"), "200.00")
        self.assertEqual(row.get("vzNp"), "0.00")
        self.assertEqual(row.get("vzUp"), "400.00")

    def test_mixed_known_and_missing_fragments_keep_known_fund_bases(self):
        if self.engine != "oca":
            self.skipTest("Recorded OCA source fixture")
        _employee, first = self._employee_payslip(20000)
        second = first.copy({"name": "Second actual remuneration"})
        second.compute_sheet()
        confirm_payslips(second)
        saved = {slip.id: deepcopy(slip._cssk_recorded_fund_bases()) for slip in first | second}
        declaration = self._mvp()
        with patch.object(type(first), "_cssk_recorded_fund_bases", lambda slip: saved[slip.id] if slip.id == first.id else False):
            declaration.action_generate()
        tree = etree.fromstring(base64.b64decode(declaration.xml_attachment_id.datas))
        row = tree.find(".//m:poistneZamestnanca", NS)
        self.assertEqual(row.get("vzNp"), "36764.00")
        self.assertEqual(row.get("vzUp"), "40000.00")
        self.assertIn(second.display_name, declaration.fund_bases_warning)
        self.assertEqual(first._cssk_recorded_fund_bases(), saved[first.id])

    def test_missing_charged_fund_uses_shared_original_and_correction_policy(self):
        if self.engine != "oca":
            self.skipTest("Recorded OCA source fixture")
        _employee, slip = self._employee_payslip(20000)
        rows = deepcopy(slip._cssk_recorded_fund_bases())
        incomplete = [row for row in rows if (row["fund"], row["side"]) != ("sickness", "employee")]
        self.assertLess(len(incomplete), len(rows))
        original = self._mvp()
        with patch.object(type(slip), "_cssk_recorded_fund_bases", return_value=incomplete):
            original.action_generate()
            self.assertIn(slip.display_name, original.fund_bases_warning)
            archived = base64.b64decode(original.xml_attachment_id.datas)
            original.action_submit()
            correction = self._mvp()
            correction.write({
                "correction_type": "corrective", "replaced_mvp_id": original.id,
            })
            with self.assertRaises(UserError):
                correction.action_generate()
            correction.fund_bases_fallback_reason = "Reviewed original historical payroll without a sickness record."
            correction.action_confirm_legacy_fund_bases()
            correction.action_generate()
            self.assertEqual(base64.b64decode(original.submitted_attachment_id.datas), archived)

    def test_engine_without_recorder_keeps_original_gross_workflow(self):
        _employee, slip = self._employee_payslip(20000)
        declaration = self._mvp()
        with patch.object(type(slip), "_cssk_recorded_fund_bases", None, create=True):
            declaration.action_generate()
            self.assertFalse(declaration.fund_bases_warning)
        tree = etree.fromstring(base64.b64decode(declaration.xml_attachment_id.datas))
        row = tree.find(".//m:poistneZamestnanca", NS)
        self.assertEqual(row.get("vzNp"), "20000.00")


@tagged("post_install", "-at_install")
class TestRetainedAnnexWithoutEngine(TransactionCase):
    def test_retained_sheet_lines_keep_original_rendering_without_engine(self):
        company = self.env["res.company"].create({"name": "Retained MVP", "country_id": self.env.ref("base.sk").id})
        self.env.user.company_ids |= company
        employee = self.env["hr.employee"].with_company(company).create({"name": "Retained employee", "company_id": company.id, "identification_id": "8501011234"})
        declaration = self.env["l10n.sk.mvp"].with_company(company).create({"company_id": company.id, "year": "2026", "month": "3"})
        self.env["cssk.payroll.employee.declaration"].create({"res_model": declaration._name, "res_id": declaration.id, "employee_id": employee.id, "company_id": company.id, "vz_base": 1234.56})
        with patch.object(type(declaration), "_get_period_payslips", return_value=None):
            row = declaration._build_annex()[0]
        self.assertTrue(row["bases"])
        self.assertEqual(set(row["bases"].values()), {"1234.56"})


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
