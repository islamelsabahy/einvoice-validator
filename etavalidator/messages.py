"""Bilingual messages. Keys are stable rule codes."""

MESSAGES = {
    "JSON_INVALID": ("File is not valid JSON: {0}", "الملف مش JSON صالح: {0}"),
    "MISSING": ("Missing required field: {0}", "حقل مطلوب ناقص: {0}"),
    "EMPTY": ("Field must not be empty: {0}", "الحقل ما ينفعش يبقى فاضي: {0}"),
    "BAD_ENUM": ("Unexpected value {1!r} for {0} (allowed: {2})", "قيمة غير متوقعة {1!r} في {0} (المسموح: {2})"),
    "BAD_DATETIME": ("{0} must be UTC ISO format like 2026-01-31T09:30:00Z, got {1!r}", "{0} لازم يبقى بصيغة UTC زي 2026-01-31T09:30:00Z وليس {1!r}"),
    "FUTURE_DATE": ("dateTimeIssued is in the future", "تاريخ الإصدار في المستقبل"),
    "BAD_NUMBER": ("{0} must be a number, got {1!r}", "{0} لازم يبقى رقم وليس {1!r}"),
    "NEGATIVE": ("{0} must not be negative", "{0} ما ينفعش يبقى سالب"),
    "LINE_SALES_TOTAL": ("Line {0}: salesTotal {1} != quantity x unit price {2}", "بند {0}: salesTotal {1} لا يساوي الكمية × سعر الوحدة {2}"),
    "LINE_NET_TOTAL": ("Line {0}: netTotal {1} != salesTotal - discount {2}", "بند {0}: netTotal {1} لا يساوي salesTotal - الخصم {2}"),
    "LINE_TAX_AMOUNT": ("Line {0}: tax {1}/{2} amount {3} != expected {4}", "بند {0}: ضريبة {1}/{2} قيمتها {3} والمتوقع {4}"),
    "LINE_TOTAL": ("Line {0}: total {1} != expected {2}", "بند {0}: total {1} والمتوقع {2}"),
    "LINE_CURRENCY": ("Line {0}: amountSold/currencyExchangeRate required when currencySold is not EGP", "بند {0}: لازم amountSold و currencyExchangeRate لما العملة مش EGP"),
    "LINE_CURRENCY_MATH": ("Line {0}: amountEGP {1} != amountSold x rate {2}", "بند {0}: amountEGP {1} لا يساوي amountSold × السعر {2}"),
    "HDR_SALES": ("totalSalesAmount {0} != sum of line salesTotal {1}", "totalSalesAmount {0} لا يساوي مجموع البنود {1}"),
    "HDR_NET": ("netAmount {0} != sum of line netTotal {1}", "netAmount {0} لا يساوي مجموع البنود {1}"),
    "HDR_DISCOUNT": ("totalDiscountAmount {0} != sum of line discounts {1}", "totalDiscountAmount {0} لا يساوي مجموع الخصومات {1}"),
    "HDR_TAX": ("taxTotals {0} = {1} but lines sum to {2}", "taxTotals {0} = {1} ومجموع البنود {2}"),
    "HDR_TAX_MISSING": ("taxTotals has no entry for tax type {0} used in lines", "taxTotals مفيهوش نوع الضريبة {0} المستخدم في البنود"),
    "HDR_TOTAL": ("totalAmount {0} != expected {1}", "totalAmount {0} والمتوقع {1}"),
    "B2C_NEEDS_ID": ("Individual receiver (type P) with total above {0} EGP should carry an id", "المستلم فرد (نوع P) والإجمالي فوق {0} جنيه لازم يكون له id"),
    "ID_FORMAT": ("{0} id {1!r} has an unexpected format for type {2}", "رقم {0} ({1!r}) شكله غير متوقع لنوع {2}"),
    "DUP_INTERNAL_ID": ("Duplicate internalID in batch: {0}", "internalID متكرر في الدفعة: {0}"),
    "NO_LINES": ("Document has no invoiceLines", "المستند مفيهوش بنود"),
    "DOC_REF": ("Credit/debit notes should reference the original invoice (references)", "إشعار الخصم/الإضافة لازم يشير للفاتورة الأصلية (references)"),
}


def render(code, args, lang="en"):
    en, ar = MESSAGES[code]
    return (ar if lang == "ar" else en).format(*args)
