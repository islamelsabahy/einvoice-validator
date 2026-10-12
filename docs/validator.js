/* Browser port of etavalidator/validator.py (the Python code is the reference).
 * tests/vectors.json is generated from Python; `node tests/test_validator.js` checks that
 * this file reports the same level, code and path for every vector.
 * Money is handled as BigInt fixed point (12 decimals) so 5001 * 14% is exact, like Decimal.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("./messages.js"));
  else root.EtaValidator = factory(root.ETA_MESSAGES);
})(typeof self !== "undefined" ? self : this, function (MESSAGES) {
  "use strict";

  var DOC_TYPES = ["C", "D", "I"];
  var PARTY_TYPES = ["B", "F", "P"];
  var ITEM_TYPES = ["EGS", "GS1"];
  var SUBTRACTED = { T4: true };
  var SCALE = 12;
  var ONE = 10n ** 12n;
  var B2C_ID_THRESHOLD = 50000n * ONE;
  var DT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
  var NUM_RE = /^([+-]?)(\d+\.?\d*|\.\d+)(?:[eE]([+-]?\d+))?$/;

  /* ---------- fixed-point decimals (BigInt scaled by 1e12) ---------- */
  function parseDec(value) {
    if (value === null || value === undefined || typeof value === "boolean") return null;
    if (typeof value !== "number" && typeof value !== "string") return null;
    var m = NUM_RE.exec(String(value).trim());
    if (!m) return null;
    var parts = m[2].split(".");
    var frac = parts[1] || "";
    var digits = BigInt((parts[0] || "0") + frac);
    var exp = SCALE - frac.length + (m[3] ? parseInt(m[3], 10) : 0);
    if (exp > 60) exp = 60; // keeps absurd exponents from allocating huge integers
    var n = exp >= 0 ? digits * 10n ** BigInt(exp) : digits / 10n ** BigInt(-exp);
    return m[1] === "-" ? -n : n;
  }
  function mul(a, b) { return (a * b) / ONE; }
  function pct(base, rate) { return (base * rate) / (ONE * 100n); }
  function abs(a) { return a < 0n ? -a : a; }

  function fmt(n, minFrac) {
    if (n === null || n === undefined) return "";
    var neg = n < 0n, s = abs(n).toString().padStart(SCALE + 1, "0");
    var int = s.slice(0, -SCALE), frac = s.slice(-SCALE).replace(/0+$/, "");
    while (frac.length < (minFrac === undefined ? 2 : minFrac)) frac += "0";
    return (neg ? "-" : "") + int + (frac ? "." + frac : "");
  }
  function quantize5(n) { // round half to even at 5 decimals, display only
    var unit = 10n ** BigInt(SCALE - 5), q = abs(n) / unit, r = abs(n) % unit, half = unit / 2n;
    if (r > half || (r === half && q % 2n === 1n)) q += 1n;
    return (n < 0n ? -q : q) * unit;
  }

  /* ---------- Python-compatible helpers ---------- */
  function truthy(v) {
    if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  }
  function isObj(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function get(o, k) { return isObj(o) && has(o, k) ? o[k] : undefined; }
  function pyStr(v) { // str() as Python would render it; only emptiness and enum membership matter
    if (typeof v === "string") return v;
    if (v === true) return "True";
    if (v === false) return "False";
    if (v !== null && typeof v === "object") return JSON.stringify(v);
    return String(v);
  }
  function repr(v) { return typeof v === "string" ? "'" + v + "'" : v === null ? "None" : JSON.stringify(v); }

  function Ctx(tol, now) { this.issues = []; this.tol = tol; this.now = now; }
  Ctx.prototype.add = function (level, code, path) {
    this.issues.push({ level: level, code: code, path: path, args: Array.prototype.slice.call(arguments, 3) });
  };
  Ctx.prototype.close = function (a, b) { return abs(a - b) <= this.tol; };
  Ctx.prototype.number = function (obj, key, path, required) {
    if (required === undefined) required = true;
    var full = path + "." + key;
    if (!has(obj, key) || obj[key] === null) {
      if (required) this.add("error", "MISSING", full, full);
      return null;
    }
    var n = parseDec(obj[key]);
    if (n === null) this.add("error", "BAD_NUMBER", full, full, repr(obj[key]));
    return n;
  };
  Ctx.prototype.text = function (obj, key, path) {
    var full = path + "." + key, v = get(obj, key);
    if (v === undefined || v === null) { this.add("error", "MISSING", full, full); return null; }
    if (typeof v === "string" && !v.trim()) { this.add("error", "EMPTY", full, full); return null; }
    return pyStr(v);
  };

  /* ---------- rules ---------- */
  function checkParty(ctx, party, path, total, isReceiver) {
    if (!isObj(party)) { ctx.add("error", "MISSING", path, path); return; }
    var ptype = ctx.text(party, "type", path);
    if (ptype && PARTY_TYPES.indexOf(ptype) < 0)
      ctx.add("error", "BAD_ENUM", path + ".type", path + ".type", repr(ptype), PARTY_TYPES.join(", "));
    var pid = party.id;
    if (!isReceiver && !truthy(pid)) ctx.add("error", "MISSING", path + ".id", path + ".id");
    if (ptype === "B" && truthy(pid) && !/^\d{9}$/.test(String(pid))) ctx.add("warning", "ID_FORMAT", path + ".id", path, repr(pid), "B");
    if (ptype === "P" && truthy(pid) && !/^\d{14}$/.test(String(pid))) ctx.add("warning", "ID_FORMAT", path + ".id", path, repr(pid), "P");
    if (isReceiver && ptype === "B" && !truthy(pid)) ctx.add("error", "MISSING", path + ".id", path + ".id");
    if (isReceiver && ptype === "P" && !truthy(pid) && total !== null && total > B2C_ID_THRESHOLD)
      ctx.add("warning", "B2C_NEEDS_ID", path + ".id", 50000);
    if (!(isReceiver && ptype === "P" && !truthy(party.name))) ctx.text(party, "name", path);
    var addr = party.address;
    if (!isObj(addr)) { ctx.add("error", "MISSING", path + ".address", path + ".address"); return; }
    ["country", "governate", "regionCity", "street", "buildingNumber"].forEach(function (key) {
      if (!truthy(addr[key])) ctx.add("error", "MISSING", path + ".address." + key, path + ".address." + key);
    });
    if (!isReceiver && (addr.branchID === undefined || addr.branchID === null || addr.branchID === ""))
      ctx.add("error", "MISSING", path + ".address.branchID", path + ".address.branchID");
  }

  function orZero(n) { return n === null || n === 0n ? 0n : n; }

  function checkLine(ctx, line, i, taxSums) {
    var path = "$.invoiceLines[" + i + "]", n = i + 1;
    if (!isObj(line)) { ctx.add("error", "MISSING", path, path); return null; }
    ctx.text(line, "description", path);
    var itype = ctx.text(line, "itemType", path);
    if (itype && ITEM_TYPES.indexOf(itype) < 0)
      ctx.add("error", "BAD_ENUM", path + ".itemType", path + ".itemType", repr(itype), ITEM_TYPES.join(", "));
    ctx.text(line, "itemCode", path);
    ctx.text(line, "unitType", path);

    var qty = ctx.number(line, "quantity", path);
    var uv = line.unitValue, unitEgp = null;
    if (!isObj(uv)) {
      ctx.add("error", "MISSING", path + ".unitValue", path + ".unitValue");
    } else {
      unitEgp = ctx.number(uv, "amountEGP", path + ".unitValue");
      var cur = has(uv, "currencySold") ? uv.currencySold : "EGP";
      if (cur !== "EGP") {
        var sold = parseDec(uv.amountSold), rate = parseDec(uv.currencyExchangeRate);
        if (sold === null || rate === null) {
          ctx.add("error", "LINE_CURRENCY", path + ".unitValue", n);
        } else if (unitEgp !== null && !ctx.close(unitEgp, mul(sold, rate))) {
          ctx.add("error", "LINE_CURRENCY_MATH", path + ".unitValue.amountEGP", n, fmt(unitEgp), fmt(mul(sold, rate)));
        }
      }
    }
    if (qty !== null && qty < 0n) ctx.add("error", "NEGATIVE", path + ".quantity", path + ".quantity");
    if (unitEgp !== null && unitEgp < 0n)
      ctx.add("error", "NEGATIVE", path + ".unitValue.amountEGP", path + ".unitValue.amountEGP");

    var sales = ctx.number(line, "salesTotal", path);
    var net = ctx.number(line, "netTotal", path);
    var total = ctx.number(line, "total", path);
    var fees = orZero(parseDec(line.totalTaxableFees));
    var diff = orZero(parseDec(line.valueDifference));
    var itemsDisc = orZero(parseDec(line.itemsDiscount));
    var disc = truthy(line.discount) ? line.discount : {};
    var discAmt = isObj(disc) ? orZero(parseDec(disc.amount)) : 0n;

    if (sales !== null && qty !== null && unitEgp !== null && !ctx.close(sales, mul(qty, unitEgp)))
      ctx.add("error", "LINE_SALES_TOTAL", path + ".salesTotal", n, fmt(sales), fmt(mul(qty, unitEgp)));
    if (net !== null && sales !== null && !ctx.close(net, sales - discAmt))
      ctx.add("error", "LINE_NET_TOTAL", path + ".netTotal", n, fmt(net), fmt(sales - discAmt));

    var base = (net === null ? 0n : net) + fees + diff, taxEffect = 0n;
    var items = line.taxableItems;
    if (!Array.isArray(items) || !items.length) {
      ctx.add("error", "MISSING", path + ".taxableItems", path + ".taxableItems");
      items = [];
    }
    items.forEach(function (t, j) {
      var tp = path + ".taxableItems[" + j + "]";
      if (!isObj(t)) { ctx.add("error", "MISSING", tp, tp); return; }
      var ttype = ctx.text(t, "taxType", tp);
      ctx.text(t, "subType", tp);
      var amount = ctx.number(t, "amount", tp);
      var rate = parseDec(t.rate);
      if (rate !== null && amount !== null && ttype) {
        var expected = pct(base, rate);
        if (!ctx.close(amount, expected))
          ctx.add("error", "LINE_TAX_AMOUNT", tp + ".amount", n, ttype, fmt(rate, 0), fmt(amount), fmt(quantize5(expected), 2));
      }
      if (amount !== null && ttype) {
        taxSums.set(ttype, (taxSums.has(ttype) ? taxSums.get(ttype) : 0n) + amount);
        taxEffect += SUBTRACTED[ttype] ? -amount : amount;
      }
    });

    if (total !== null && net !== null) {
      var expectedTotal = base + taxEffect - itemsDisc;
      if (!ctx.close(total, expectedTotal)) ctx.add("error", "LINE_TOTAL", path + ".total", n, fmt(total), fmt(expectedTotal));
    }
    return { sales: orZero(sales), net: orZero(net), total: orZero(total), disc: discAmt };
  }

  function parseIssued(stamp) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/.exec(stamp);
    var y = +m[1], mo = +m[2], d = +m[3], h = +m[4], mi = +m[5], s = +m[6];
    var t = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
    if (mo < 1 || mo > 12 || h > 23 || mi > 59 || s > 59 || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d || y < 1) return null;
    return t;
  }

  function validateDocument(doc, opts) {
    opts = opts || {};
    var tol = parseDec(opts.tolerance === undefined ? "0.01" : opts.tolerance);
    if (tol === null) tol = parseDec("0.01");
    var now = opts.now ? new Date(opts.now) : new Date();
    var ctx = new Ctx(tol, now);
    if (!isObj(doc)) { ctx.add("error", "MISSING", "$", "$"); return ctx.issues; }

    var dtype = ctx.text(doc, "documentType", "$");
    if (dtype && DOC_TYPES.indexOf(dtype) < 0)
      ctx.add("error", "BAD_ENUM", "$.documentType", "documentType", repr(dtype), DOC_TYPES.join(", "));
    ctx.text(doc, "documentTypeVersion", "$");
    ctx.text(doc, "internalID", "$");
    ctx.text(doc, "taxpayerActivityCode", "$");

    var stamp = ctx.text(doc, "dateTimeIssued", "$");
    if (stamp) {
      if (!DT_RE.test(stamp)) {
        ctx.add("error", "BAD_DATETIME", "$.dateTimeIssued", "dateTimeIssued", repr(stamp));
      } else {
        var issued = parseIssued(stamp);
        if (!issued) ctx.add("error", "BAD_DATETIME", "$.dateTimeIssued", "dateTimeIssued", repr(stamp));
        else if (issued.getTime() > now.getTime()) ctx.add("error", "FUTURE_DATE", "$.dateTimeIssued");
      }
    }

    var totalAmount = ctx.number(doc, "totalAmount", "$");
    checkParty(ctx, doc.issuer, "$.issuer", null, false);
    checkParty(ctx, doc.receiver, "$.receiver", totalAmount, true);

    if ((dtype === "C" || dtype === "D") && !truthy(doc.references)) ctx.add("warning", "DOC_REF", "$.references");

    var lines = doc.invoiceLines;
    if (!Array.isArray(lines) || !lines.length) { ctx.add("error", "NO_LINES", "$.invoiceLines"); return ctx.issues; }

    var taxSums = new Map(), sums = { sales: 0n, net: 0n, total: 0n, disc: 0n };
    lines.forEach(function (line, i) {
      var res = checkLine(ctx, line, i, taxSums);
      if (res) for (var k in sums) sums[k] += res[k];
    });

    var totalSales = ctx.number(doc, "totalSalesAmount", "$");
    var netAmount = ctx.number(doc, "netAmount", "$");
    var totalDisc = parseDec(doc.totalDiscountAmount);
    var extra = orZero(parseDec(doc.extraDiscountAmount));

    if (totalSales !== null && !ctx.close(totalSales, sums.sales)) ctx.add("error", "HDR_SALES", "$.totalSalesAmount", fmt(totalSales), fmt(sums.sales));
    if (netAmount !== null && !ctx.close(netAmount, sums.net)) ctx.add("error", "HDR_NET", "$.netAmount", fmt(netAmount), fmt(sums.net));
    if (totalDisc !== null && !ctx.close(totalDisc, sums.disc)) ctx.add("error", "HDR_DISCOUNT", "$.totalDiscountAmount", fmt(totalDisc), fmt(sums.disc));

    var declared = {};
    (Array.isArray(doc.taxTotals) ? doc.taxTotals : []).forEach(function (t) {
      if (isObj(t) && truthy(t.taxType)) declared[pyStr(t.taxType)] = parseDec(t.amount);
    });
    taxSums.forEach(function (sum, ttype) {
      if (!has(declared, ttype)) ctx.add("error", "HDR_TAX_MISSING", "$.taxTotals", ttype);
      else if (declared[ttype] !== null && !ctx.close(declared[ttype], sum))
        ctx.add("error", "HDR_TAX", "$.taxTotals", ttype, fmt(declared[ttype]), fmt(sum));
    });

    if (totalAmount !== null) {
      var expectedTotal = sums.total - extra;
      if (!ctx.close(totalAmount, expectedTotal)) ctx.add("error", "HDR_TOTAL", "$.totalAmount", fmt(totalAmount), fmt(expectedTotal));
    }
    return ctx.issues;
  }

  function validateData(data, opts) {
    var docs = isObj(data) ? (has(data, "documents") ? data.documents : [data]) : data;
    if (!Array.isArray(docs)) docs = [docs];
    var issues = [], seen = {};
    docs.forEach(function (doc, idx) {
      var prefix = docs.length > 1 ? "[" + idx + "]" : "";
      validateDocument(doc, opts).forEach(function (it) {
        issues.push({ level: it.level, code: it.code, path: prefix + it.path, args: it.args });
      });
      var iid = isObj(doc) ? doc.internalID : undefined;
      if (typeof iid === "string" || (typeof iid === "number" && Number.isInteger(iid))) {
        var key = typeof iid + ":" + iid;
        if (has(seen, key)) issues.push({ level: "error", code: "DUP_INTERNAL_ID", path: prefix + "$.internalID", args: [iid] });
        seen[key] = true;
      }
    });
    return issues;
  }

  function validateText(text, opts) {
    var data;
    try { data = JSON.parse(text); }
    catch (e) { return [{ level: "error", code: "JSON_INVALID", path: "$", args: [String(e.message)] }]; }
    return validateData(data, opts);
  }

  /* Message split into literal text and substituted values, so a UI can isolate the values (RTL). */
  function messageParts(issue, lang) {
    var pair = MESSAGES[issue.code] || [issue.code, issue.code];
    var tpl = pair[lang === "ar" ? 1 : 0], parts = [], last = 0, m, re = /\{(\d+)(!r)?\}/g;
    while ((m = re.exec(tpl))) {
      if (m.index > last) parts.push({ text: tpl.slice(last, m.index), arg: false });
      var v = issue.args[+m[1]];
      if (v !== undefined) parts.push({ text: String(v), arg: true });
      last = re.lastIndex;
    }
    if (last < tpl.length) parts.push({ text: tpl.slice(last), arg: false });
    return parts;
  }
  function message(issue, lang) {
    return messageParts(issue, lang).map(function (p) { return p.text; }).join("");
  }

  return { validateDocument: validateDocument, validateData: validateData, validateText: validateText, message: message, messageParts: messageParts };
});
