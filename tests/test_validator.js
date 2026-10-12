// Parity check: the browser validator must report the same level, code and path as the Python reference.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const V = require("../docs/validator.js");
const MSG = require("../docs/messages.js");

const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, "vectors.json"), "utf8"));
for (const v of vectors) {
  const got = V.validateData(v.data, { tolerance: v.tolerance, now: v.now }).map((i) => [i.level, i.code, i.path]);
  assert.deepStrictEqual(got, v.expected, v.name);
}

// every message renders in both languages without leftover placeholders
for (const code of Object.keys(MSG)) {
  for (const lang of ["en", "ar"]) {
    const text = V.message({ code, args: ["a", "b", "c", "d", "e"] }, lang);
    assert.ok(text && !/[{}]/.test(text), code + " " + lang);
  }
}
assert.strictEqual(V.validateText("{nope")[0].code, "JSON_INVALID");
assert.notStrictEqual(V.message(V.validateText("{nope")[0], "en"), V.message(V.validateText("{nope")[0], "ar"));
console.log(`ok - ${vectors.length} shared vectors + message rendering`);
