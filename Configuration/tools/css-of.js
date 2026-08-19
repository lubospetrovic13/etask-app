// Prints the compiled component CSS embedded in an Angular Package Format .mjs file.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const MARK = 'styles: [';
const seen = new Set();
let i = 0;
for (;;) {
  i = src.indexOf(MARK, i);
  if (i === -1) break;
  let j = i + MARK.length;
  if (src[j] !== '"') { i = j; continue; }
  // walk the JS string literal, honouring escapes
  let k = j + 1;
  while (k < src.length) {
    if (src[k] === '\\') { k += 2; continue; }
    if (src[k] === '"') break;
    k++;
  }
  const lit = src.slice(j, k + 1);
  i = k + 1;
  let css;
  try { css = JSON.parse(lit); } catch (e) { continue; }
  if (seen.has(css)) continue;
  seen.add(css);
  console.log(css.split('}').join('}\n'));
}
