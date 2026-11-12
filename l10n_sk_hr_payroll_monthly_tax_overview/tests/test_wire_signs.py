# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The authority adds signed rows5–7; an XSD check alone cannot detect this."""
from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged("post_install", "-at_install")
class TestPrehladWireSigns(TransactionCase):
    def test_wire_recovery_and_zero_preserve_internal_amounts(self):
        model = self.env["l10n.sk.prehlad"]
        self.assertEqual(model._wire_reduction_amount(20), "-20.00")
        self.assertEqual(model._wire_reduction_amount(-20), "20.00")
        self.assertEqual(model._wire_reduction_amount(0), "0.00")

    def test_paid_child_bonus_is_negative_on_the_wire(self):
        company = self.env["res.company"].create({
            "name": "Synthetic monthly tax employer", "country_id": self.env.ref("base.sk").id,
            "l10n_sk_dic": "1234567890", "company_registry": "12345679",
            "currency_id": self.env.ref("base.EUR").id})
        self.env.user.company_ids |= company
        for year in (2026, 2027):
            with self.subTest(year=year):
                report = self.env["l10n.sk.prehlad"].with_company(company).create({
                    "company_id": company.id, "year": str(year), "month": "1",
                    "version_id": self.env.ref(
                        "l10n_sk_hr_payroll_monthly_tax_overview.prehlad_version_2026").id})
                context = report._declaration_render_context({"aggregate": {
                    "GROSS": 1000, "INCOMETAX": 100, "CHILD_BONUS": 20}})
                raw = self.env["ir.qweb"]._render(report.version_id.xml_template_ref_id.id, context)
                root = etree.fromstring(str(raw).encode())
                with file_open("l10n_sk_hr_payroll_monthly_tax_overview/data/prehlad2026.xsd", "rb") as source:
                    etree.XMLSchema(etree.parse(source)).assertValid(root)
                values = {code: float(root.findtext("./telo/cast1/" + code) or 0)
                          for code in ("r04", "r05", "r06", "r07", "r08")}
                # Official PREHLADv26 eForm form624, vypocet_t1r8:
                # r8 = r4 + r5 + r6 + r7; paid bonuses REDUCE remittance.
                self.assertEqual(values["r08"], sum(values[code] for code in
                    ("r04", "r05", "r06", "r07")), values)
                self.assertEqual(values["r05"], -20)
                self.assertEqual(values["r08"], 80)
                self.assertEqual(float(root.findtext("./telo/cast2/rB")), 20)
