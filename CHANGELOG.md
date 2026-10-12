# Changelog

## 0.2.0
- Browser version (`docs/`, GitHub Pages): paste, drop or open a JSON file and validate it client-side, English/Arabic UI, copy or download the report. A JS port of the rules with exact fixed-point money (BigInt), no dependencies.
- `validate_data()` for already-parsed JSON (`validate_file` now uses it).
- Fixed: an impossible date such as `2026-13-45T00:00:00Z` crashed the validator; it is now a `BAD_DATETIME` error.
- Fixed: malformed shapes (for example `taxTotals` as a number, or an unhashable `taxType`) raised instead of reporting; documents with no `internalID` are no longer reported as duplicates of each other.
- Issue paths for lines are now `$.invoiceLines[i]...` like every other path.
- Python and JS are checked against each other: `tests/vectors.json` is generated from Python by `scripts/build_web_data.py` and replayed by `node tests/test_validator.js` in CI; a unit test fails if the generated files go stale.

## 0.1.0
- First release: structure, enum, date and arithmetic checks for ETA v1.0 invoices; English/Arabic messages; batch mode.
