import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest import mock

from etavalidator import validate_data, validate_document, validate_file

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "sample-data")
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def load(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as fh:
        return json.load(fh)


def codes(doc, level=None, **kw):
    kw.setdefault("now", NOW)
    return [i.code for i in validate_document(doc, **kw) if level in (None, i.level)]


class ValidTests(unittest.TestCase):
    def test_valid_sample_has_no_findings(self):
        self.assertEqual(validate_document(load("valid_invoice.json"), now=NOW), [])

    def test_invalid_sample_reports_three_errors(self):
        self.assertEqual(sorted(codes(load("invalid_invoice.json"), "error")),
                         ["BAD_DATETIME", "HDR_TOTAL", "LINE_TOTAL"])


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.doc = load("valid_invoice.json")

    def test_missing_field(self):
        del self.doc["internalID"]
        self.assertIn("MISSING", codes(self.doc, "error"))

    def test_bad_document_type(self):
        self.doc["documentType"] = "X"
        self.assertIn("BAD_ENUM", codes(self.doc, "error"))

    def test_future_date(self):
        self.doc["dateTimeIssued"] = "2030-01-01T00:00:00Z"
        self.assertIn("FUTURE_DATE", codes(self.doc, "error"))

    def test_impossible_date_is_an_error_not_a_crash(self):
        self.doc["dateTimeIssued"] = "2026-13-45T00:00:00Z"
        self.assertEqual(codes(self.doc, "error"), ["BAD_DATETIME"])

    def test_no_lines(self):
        self.doc["invoiceLines"] = []
        self.assertEqual(codes(self.doc, "error"), ["NO_LINES"])

    def test_issuer_needs_branch(self):
        del self.doc["issuer"]["address"]["branchID"]
        self.assertIn("MISSING", codes(self.doc, "error"))

    def test_credit_note_without_reference_warns(self):
        self.doc["documentType"] = "C"
        self.assertIn("DOC_REF", codes(self.doc, "warning"))

    def test_individual_over_threshold_without_id_warns(self):
        self.doc["receiver"] = {"type": "P", "address": self.doc["receiver"]["address"]}
        self.assertNotIn("B2C_NEEDS_ID", codes(self.doc, "warning"))  # 16,531 EGP is under the threshold
        with mock.patch("etavalidator.validator.B2C_ID_THRESHOLD", Decimal("10000")):
            self.assertIn("B2C_NEEDS_ID", codes(self.doc, "warning"))
        self.assertNotIn("MISSING", codes(self.doc, "error"))

    def test_business_receiver_needs_id(self):
        del self.doc["receiver"]["id"]
        self.assertIn("MISSING", codes(self.doc, "error"))

    def test_bad_tax_id_format_warns(self):
        self.doc["issuer"]["id"] = "123"
        self.assertIn("ID_FORMAT", codes(self.doc, "warning"))


class ArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.doc = load("valid_invoice.json")

    def test_sales_total_mismatch(self):
        self.doc["invoiceLines"][0]["salesTotal"] = 9000
        self.assertIn("LINE_SALES_TOTAL", codes(self.doc, "error"))

    def test_net_total_mismatch(self):
        self.doc["invoiceLines"][0]["netTotal"] = 9999
        self.assertIn("LINE_NET_TOTAL", codes(self.doc, "error"))

    def test_vat_amount_mismatch(self):
        self.doc["invoiceLines"][0]["taxableItems"][0]["amount"] = 1000
        self.assertIn("LINE_TAX_AMOUNT", codes(self.doc, "error"))

    def test_header_tax_mismatch(self):
        self.doc["taxTotals"][0]["amount"] = 1
        self.assertIn("HDR_TAX", codes(self.doc, "error"))

    def test_header_tax_type_missing(self):
        self.doc["taxTotals"] = []
        self.assertIn("HDR_TAX_MISSING", codes(self.doc, "error"))

    def test_header_discount_mismatch(self):
        self.doc["totalDiscountAmount"] = 0
        self.assertIn("HDR_DISCOUNT", codes(self.doc, "error"))

    def test_rounding_within_tolerance_passes(self):
        self.doc["totalAmount"] += 0.005
        self.assertEqual(codes(self.doc, "error"), [])

    def test_rounding_outside_tolerance_fails(self):
        self.doc["totalAmount"] += 0.05
        self.assertIn("HDR_TOTAL", codes(self.doc, "error"))
        self.assertEqual(codes(self.doc, "error", tolerance="0.10"), [])

    def test_foreign_currency_needs_rate(self):
        self.doc["invoiceLines"][0]["unitValue"]["currencySold"] = "USD"
        self.assertIn("LINE_CURRENCY", codes(self.doc, "error"))

    def test_foreign_currency_math(self):
        uv = self.doc["invoiceLines"][0]["unitValue"]
        uv.update(currencySold="USD", amountSold=20, currencyExchangeRate=50)
        self.assertEqual(codes(self.doc, "error"), [])
        uv["currencyExchangeRate"] = 40
        self.assertIn("LINE_CURRENCY_MATH", codes(self.doc, "error"))

    def test_withholding_tax_is_subtracted(self):
        line = self.doc["invoiceLines"][1]
        line["taxableItems"].append({"taxType": "T4", "amount": 50.01, "subType": "W010", "rate": 1})
        line["total"] = round(5001 + 700.14 - 50.01, 2)
        self.doc["taxTotals"].append({"taxType": "T4", "amount": 50.01})
        self.doc["totalAmount"] = round(10830 + line["total"], 2)
        self.assertEqual(codes(self.doc, "error"), [])

    def test_items_discount_reduces_total(self):
        line = self.doc["invoiceLines"][1]
        line["itemsDiscount"] = 10
        line["total"] = round(5701.14 - 10, 2)
        self.doc["totalAmount"] = round(10830 + line["total"], 2)
        self.assertEqual(codes(self.doc, "error"), [])

    def test_extra_discount(self):
        self.doc["extraDiscountAmount"] = 100
        self.doc["totalAmount"] = 16431.14
        self.assertEqual(codes(self.doc, "error"), [])


class WebDataTests(unittest.TestCase):
    """docs/messages.js and tests/vectors.json are generated; fail if they drift from the Python code."""

    def test_generated_web_files_are_current(self):
        import importlib.util
        path = os.path.join(HERE, "..", "scripts", "build_web_data.py")
        spec = importlib.util.spec_from_file_location("build_web_data", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.stale(), [], "run: python scripts/build_web_data.py")


class RobustnessTests(unittest.TestCase):
    def test_malformed_shapes_never_raise(self):
        base = load("valid_invoice.json")
        for key, bad in (("taxTotals", 5), ("taxTotals", True), ("invoiceLines", "x"),
                         ("issuer", []), ("receiver", 3), ("references", {})):
            doc = copy.deepcopy(base)
            doc[key] = bad
            validate_document(doc, now=NOW)  # must not raise

    def test_unhashable_tax_type_does_not_raise(self):
        doc = load("valid_invoice.json")
        doc["invoiceLines"][0]["taxableItems"][0]["taxType"] = []
        validate_document(doc, now=NOW)


class FileTests(unittest.TestCase):
    def write(self, payload):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_invalid_json(self):
        self.assertEqual(validate_file(self.write("{nope"))[0].code, "JSON_INVALID")

    def test_missing_file(self):
        self.assertEqual(validate_file("/no/such/file.json")[0].code, "JSON_INVALID")

    def test_batch_duplicate_internal_id(self):
        d = load("valid_invoice.json")
        path = self.write({"documents": [d, copy.deepcopy(d)]})
        self.assertIn("DUP_INTERNAL_ID", [i.code for i in validate_file(path, now=NOW)])

    def test_missing_ids_are_not_reported_as_duplicates(self):
        a, b = load("valid_invoice.json"), load("valid_invoice.json")
        del a["internalID"], b["internalID"]
        self.assertNotIn("DUP_INTERNAL_ID", [i.code for i in validate_data([a, b], now=NOW)])

    def test_scalar_input_does_not_crash(self):
        self.assertEqual([i.code for i in validate_data(5, now=NOW)], ["MISSING"])

    def test_batch_paths_are_prefixed(self):
        d = load("valid_invoice.json")
        bad = copy.deepcopy(d)
        bad["internalID"] = "X"
        bad["totalAmount"] = 1
        issues = validate_file(self.write([d, bad]), now=NOW)
        self.assertTrue(all(i.path.startswith("[1]") for i in issues))

    def test_messages_in_both_languages(self):
        issue = validate_file(self.write("{nope"))[0]
        self.assertNotEqual(issue.message("en"), issue.message("ar"))


if __name__ == "__main__":
    unittest.main()
