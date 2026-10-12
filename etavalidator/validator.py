"""Rule engine. Pure standard library; amounts use Decimal.

Scope: structure, enums, date format and arithmetic consistency of an ETA
e-invoice v1.0 JSON document *before* signing and submission. It cannot know
ETA's live code lists or business rules; it is a pre-flight check, not a
replacement for ETA's own validation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, List, Optional

from .messages import render

DOC_TYPES = {"I", "C", "D"}          # invoice, credit note, debit note
PARTY_TYPES = {"B", "P", "F"}        # business, person, foreigner
ITEM_TYPES = {"GS1", "EGS"}
SUBTRACTED_TAXES = {"T4"}            # withholding tax reduces the payable total
B2C_ID_THRESHOLD = Decimal("50000")
DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class Issue:
    level: str          # "error" or "warning"
    code: str
    path: str
    args: tuple = ()

    def message(self, lang: str = "en") -> str:
        return render(self.code, self.args, lang)


def _num(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class _Ctx:
    def __init__(self, tol: Decimal, now: datetime):
        self.issues: List[Issue] = []
        self.tol = tol
        self.now = now

    def add(self, level, code, path, *args):
        self.issues.append(Issue(level, code, path, tuple(args)))

    def close(self, a: Decimal, b: Decimal) -> bool:
        return abs(a - b) <= self.tol

    def number(self, obj: dict, key: str, path: str, required=True) -> Optional[Decimal]:
        if key not in obj or obj[key] is None:
            if required:
                self.add("error", "MISSING", f"{path}.{key}", f"{path}.{key}")
            return None
        n = _num(obj[key])
        if n is None:
            self.add("error", "BAD_NUMBER", f"{path}.{key}", f"{path}.{key}", obj[key])
        return n

    def text(self, obj: dict, key: str, path: str) -> Optional[str]:
        v = obj.get(key)
        if v is None:
            self.add("error", "MISSING", f"{path}.{key}", f"{path}.{key}")
            return None
        if isinstance(v, str) and not v.strip():
            self.add("error", "EMPTY", f"{path}.{key}", f"{path}.{key}")
            return None
        return str(v)


def _check_party(ctx: _Ctx, party: Any, path: str, total: Optional[Decimal], is_receiver: bool):
    if not isinstance(party, dict):
        ctx.add("error", "MISSING", path, path)
        return
    ptype = ctx.text(party, "type", path)
    if ptype and ptype not in PARTY_TYPES:
        ctx.add("error", "BAD_ENUM", f"{path}.type", f"{path}.type", ptype, ", ".join(sorted(PARTY_TYPES)))
    pid = party.get("id")
    if not is_receiver and not pid:
        ctx.add("error", "MISSING", f"{path}.id", f"{path}.id")
    if ptype == "B" and pid and not re.fullmatch(r"\d{9}", str(pid)):
        ctx.add("warning", "ID_FORMAT", f"{path}.id", path, pid, "B")
    if ptype == "P" and pid and not re.fullmatch(r"\d{14}", str(pid)):
        ctx.add("warning", "ID_FORMAT", f"{path}.id", path, pid, "P")
    if is_receiver and ptype == "B" and not pid:
        ctx.add("error", "MISSING", f"{path}.id", f"{path}.id")
    if is_receiver and ptype == "P" and not pid and total is not None and total > B2C_ID_THRESHOLD:
        ctx.add("warning", "B2C_NEEDS_ID", f"{path}.id", int(B2C_ID_THRESHOLD))
    # An anonymous natural-person receiver may omit the name; everyone else needs one.
    if not (is_receiver and ptype == "P" and not party.get("name")):
        ctx.text(party, "name", path)
    addr = party.get("address")
    if not isinstance(addr, dict):
        ctx.add("error", "MISSING", f"{path}.address", f"{path}.address")
        return
    for key in ("country", "governate", "regionCity", "street", "buildingNumber"):
        if not addr.get(key):
            ctx.add("error", "MISSING", f"{path}.address.{key}", f"{path}.address.{key}")
    if not is_receiver and addr.get("branchID") in (None, ""):
        ctx.add("error", "MISSING", f"{path}.address.branchID", f"{path}.address.branchID")


def _check_line(ctx: _Ctx, line: Any, i: int, tax_sums: dict) -> Optional[dict]:
    path = f"$.invoiceLines[{i}]"
    n = i + 1
    if not isinstance(line, dict):
        ctx.add("error", "MISSING", path, path)
        return None
    ctx.text(line, "description", path)
    itype = ctx.text(line, "itemType", path)
    if itype and itype not in ITEM_TYPES:
        ctx.add("error", "BAD_ENUM", f"{path}.itemType", f"{path}.itemType", itype, ", ".join(sorted(ITEM_TYPES)))
    ctx.text(line, "itemCode", path)
    ctx.text(line, "unitType", path)

    qty = ctx.number(line, "quantity", path)
    uv = line.get("unitValue")
    unit_egp = None
    if not isinstance(uv, dict):
        ctx.add("error", "MISSING", f"{path}.unitValue", f"{path}.unitValue")
    else:
        unit_egp = ctx.number(uv, "amountEGP", f"{path}.unitValue")
        cur = uv.get("currencySold", "EGP")
        if cur != "EGP":
            sold, rate = _num(uv.get("amountSold")), _num(uv.get("currencyExchangeRate"))
            if sold is None or rate is None:
                ctx.add("error", "LINE_CURRENCY", f"{path}.unitValue", n)
            elif unit_egp is not None and not ctx.close(unit_egp, sold * rate):
                ctx.add("error", "LINE_CURRENCY_MATH", f"{path}.unitValue.amountEGP", n, unit_egp, sold * rate)
    for key in ("quantity",):
        if qty is not None and qty < 0:
            ctx.add("error", "NEGATIVE", f"{path}.{key}", f"{path}.{key}")
    if unit_egp is not None and unit_egp < 0:
        ctx.add("error", "NEGATIVE", f"{path}.unitValue.amountEGP", f"{path}.unitValue.amountEGP")

    sales = ctx.number(line, "salesTotal", path)
    net = ctx.number(line, "netTotal", path)
    total = ctx.number(line, "total", path)
    fees = _num(line.get("totalTaxableFees")) or Decimal(0)
    diff = _num(line.get("valueDifference")) or Decimal(0)
    items_disc = _num(line.get("itemsDiscount")) or Decimal(0)
    disc = line.get("discount") or {}
    disc_amt = _num(disc.get("amount")) or Decimal(0) if isinstance(disc, dict) else Decimal(0)

    if None not in (sales, qty, unit_egp) and not ctx.close(sales, qty * unit_egp):
        ctx.add("error", "LINE_SALES_TOTAL", f"{path}.salesTotal", n, sales, qty * unit_egp)
    if None not in (net, sales) and not ctx.close(net, sales - disc_amt):
        ctx.add("error", "LINE_NET_TOTAL", f"{path}.netTotal", n, net, sales - disc_amt)

    taxable_base = (net or Decimal(0)) + fees + diff
    tax_effect = Decimal(0)
    items = line.get("taxableItems")
    if not isinstance(items, list) or not items:
        ctx.add("error", "MISSING", f"{path}.taxableItems", f"{path}.taxableItems")
        items = []
    for j, t in enumerate(items):
        tp = f"{path}.taxableItems[{j}]"
        if not isinstance(t, dict):
            ctx.add("error", "MISSING", tp, tp)
            continue
        ttype = ctx.text(t, "taxType", tp)
        ctx.text(t, "subType", tp)
        amount = ctx.number(t, "amount", tp)
        rate = _num(t.get("rate"))
        if rate is not None and amount is not None and ttype:
            expected = (taxable_base * rate / 100)
            if not ctx.close(amount, expected):
                ctx.add("error", "LINE_TAX_AMOUNT", f"{tp}.amount", n, ttype, rate, amount, expected.quantize(Decimal("0.00001")))
        if amount is not None and ttype:
            tax_sums[ttype] = tax_sums.get(ttype, Decimal(0)) + amount
            tax_effect += -amount if ttype in SUBTRACTED_TAXES else amount

    if total is not None and net is not None:
        expected_total = taxable_base + tax_effect - items_disc
        if not ctx.close(total, expected_total):
            ctx.add("error", "LINE_TOTAL", f"{path}.total", n, total, expected_total)
    return {"sales": sales or Decimal(0), "net": net or Decimal(0), "total": total or Decimal(0), "disc": disc_amt}


def validate_document(doc: Any, *, tolerance: str = "0.01", now: Optional[datetime] = None) -> List[Issue]:
    """Validate one document dict. Returns a list of Issue (empty means no findings)."""
    ctx = _Ctx(Decimal(tolerance), now or datetime.now(timezone.utc))
    if not isinstance(doc, dict):
        ctx.add("error", "MISSING", "$", "$")
        return ctx.issues

    dtype = ctx.text(doc, "documentType", "$")
    if dtype and dtype not in DOC_TYPES:
        ctx.add("error", "BAD_ENUM", "$.documentType", "documentType", dtype, ", ".join(sorted(DOC_TYPES)))
    ctx.text(doc, "documentTypeVersion", "$")
    ctx.text(doc, "internalID", "$")
    ctx.text(doc, "taxpayerActivityCode", "$")

    stamp = ctx.text(doc, "dateTimeIssued", "$")
    if stamp:
        if not DT_RE.match(stamp):
            ctx.add("error", "BAD_DATETIME", "$.dateTimeIssued", "dateTimeIssued", stamp)
        else:
            try:
                issued = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:  # matches the shape but is not a real date, e.g. month 13
                ctx.add("error", "BAD_DATETIME", "$.dateTimeIssued", "dateTimeIssued", stamp)
            else:
                if issued > ctx.now:
                    ctx.add("error", "FUTURE_DATE", "$.dateTimeIssued")

    total_amount = ctx.number(doc, "totalAmount", "$")
    _check_party(ctx, doc.get("issuer"), "$.issuer", None, False)
    _check_party(ctx, doc.get("receiver"), "$.receiver", total_amount, True)

    if dtype in ("C", "D") and not doc.get("references"):
        ctx.add("warning", "DOC_REF", "$.references")

    lines = doc.get("invoiceLines")
    if not isinstance(lines, list) or not lines:
        ctx.add("error", "NO_LINES", "$.invoiceLines")
        return ctx.issues

    tax_sums: dict = {}
    sums = {"sales": Decimal(0), "net": Decimal(0), "total": Decimal(0), "disc": Decimal(0)}
    for i, line in enumerate(lines):
        res = _check_line(ctx, line, i, tax_sums)
        if res:
            for k in sums:
                sums[k] += res[k]

    total_sales = ctx.number(doc, "totalSalesAmount", "$")
    net_amount = ctx.number(doc, "netAmount", "$")
    total_disc = _num(doc.get("totalDiscountAmount"))
    extra = _num(doc.get("extraDiscountAmount")) or Decimal(0)

    if total_sales is not None and not ctx.close(total_sales, sums["sales"]):
        ctx.add("error", "HDR_SALES", "$.totalSalesAmount", total_sales, sums["sales"])
    if net_amount is not None and not ctx.close(net_amount, sums["net"]):
        ctx.add("error", "HDR_NET", "$.netAmount", net_amount, sums["net"])
    if total_disc is not None and not ctx.close(total_disc, sums["disc"]):
        ctx.add("error", "HDR_DISCOUNT", "$.totalDiscountAmount", total_disc, sums["disc"])

    declared = {}
    tax_totals = doc.get("taxTotals")
    for t in tax_totals if isinstance(tax_totals, list) else []:
        if isinstance(t, dict) and t.get("taxType"):
            declared[str(t["taxType"])] = _num(t.get("amount"))
    for ttype, expected in tax_sums.items():
        if ttype not in declared:
            ctx.add("error", "HDR_TAX_MISSING", "$.taxTotals", ttype)
        elif declared[ttype] is not None and not ctx.close(declared[ttype], expected):
            ctx.add("error", "HDR_TAX", "$.taxTotals", ttype, declared[ttype], expected)

    if total_amount is not None:
        expected_total = sums["total"] - extra
        if not ctx.close(total_amount, expected_total):
            ctx.add("error", "HDR_TOTAL", "$.totalAmount", total_amount, expected_total)
    return ctx.issues


def validate_data(data: Any, **kw) -> List[Issue]:
    """Validate parsed JSON: one document, a list of documents, or {"documents": [...]}."""
    if isinstance(data, dict):
        docs = data.get("documents", [data])
    else:
        docs = data
    docs = list(docs) if isinstance(docs, list) else [docs]
    issues: List[Issue] = []
    seen = set()
    for idx, doc in enumerate(docs):
        prefix = f"[{idx}]" if len(docs) > 1 else ""
        for it in validate_document(doc, **kw):
            issues.append(Issue(it.level, it.code, prefix + it.path, it.args))
        iid = doc.get("internalID") if isinstance(doc, dict) else None
        if isinstance(iid, (str, int)) and not isinstance(iid, bool):
            if iid in seen:
                issues.append(Issue("error", "DUP_INTERNAL_ID", f"{prefix}$.internalID", (iid,)))
            seen.add(iid)
    return issues


def validate_file(path: str, **kw) -> List[Issue]:
    """Validate a JSON file holding one document, a list, or {"documents": [...]}."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return [Issue("error", "JSON_INVALID", path, (str(exc),))]
    return validate_data(data, **kw)
