# eta-einvoice-validator

[![CI](https://github.com/islamelsabahy/eta-einvoice-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/islamelsabahy/eta-einvoice-validator/actions/workflows/ci.yml)

**EN** — An offline pre-flight checker for Egyptian Tax Authority (ETA) e-invoice JSON (v1.0 document layout). It catches the mistakes that cause rejections *before* you sign and submit: missing fields, wrong enums, bad date format, and arithmetic that does not add up (line totals, VAT, header totals). Python 3.9+, standard library only, messages in English and Arabic.

**AR** — أداة بتفحص ملف JSON للفاتورة الإلكترونية (مصلحة الضرائب المصرية) قبل التوقيع والإرسال، من غير إنترنت. بتلقط الأخطاء اللي بتسبب رفض الفاتورة: حقول ناقصة، قيم غلط، صيغة تاريخ غلط، وحسابات مش مظبوطة (إجمالي البند، الضريبة، إجماليات الفاتورة). رسائل الخطأ بالعربي والإنجليزي.

> **Not an official tool.** It checks structure and arithmetic against the documented v1.0 layout. It does not know ETA's live code lists (item codes, activity codes, tax subtypes), does not sign documents, and does not call ETA. A document that passes here can still be rejected by ETA: always confirm against the [official SDK](https://sdk.invoicing.eta.gov.eg).
>
> **أداة غير رسمية.** بتفحص الهيكل والحسابات بس، ومش بتعرف قوائم الأكواد الحية ولا بتوقّع ولا بتتصل بالمصلحة. نجاح الفحص هنا مش ضمان قبول الفاتورة.

## Use / الاستخدام

```bash
python -m etavalidator sample-data/valid_invoice.json
python -m etavalidator sample-data/invalid_invoice.json --lang ar
python -m etavalidator batch.json --tolerance 0.05 --strict
```

Input can be one document, a JSON list, or `{"documents": [...]}`. Exit code is `0` when clean and `1` when there are errors (or warnings with `--strict`), so it drops into a CI job or a pre-submission script.

```python
from etavalidator import validate_document
for issue in validate_document(doc):
    print(issue.level, issue.path, issue.message("ar"))
```

## What it checks / الفحوصات

| Area | Rules |
|---|---|
| Header | required fields, `documentType` in I/C/D, UTC `dateTimeIssued` (`...Z`) not in the future, credit/debit note should carry `references` (warning) |
| Parties | issuer id + branchID, receiver id for type B, address fields, tax-id shape (9 digits for B, 14 for P: warning), individual receiver above 50,000 EGP should carry an id (warning) |
| Lines | `salesTotal = quantity × amountEGP`, `netTotal = salesTotal − discount`, each tax `amount = rate% × (netTotal + fees + valueDifference)`, `total = base + taxes − itemsDiscount` (T4 withholding is subtracted), foreign currency needs `amountSold` and rate and `amountEGP = amountSold × rate` |
| Totals | `totalSalesAmount`, `netAmount`, `totalDiscountAmount`, per-type `taxTotals`, `totalAmount = Σ line totals − extraDiscountAmount` |
| Batch | duplicate `internalID` |

Rounding differences up to `--tolerance` (default 0.01 EGP) are accepted.

## Limits / حدود الأداة

- The formulas follow the publicly documented v1.0 layout as I understand it; if ETA changes a rule, or a rule is missing here, please open an issue with a (fictional or anonymised) sample.
- All sample data is fictional. Never commit real invoices or tax ids.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Related

- [awesome-odoo-egypt](https://github.com/islamelsabahy/awesome-odoo-egypt): ETA integration checklist and resources
- [odoo-real-estate-addons](https://github.com/islamelsabahy/odoo-real-estate-addons)

## License

MIT
