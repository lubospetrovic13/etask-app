// Reports which declaration wins for a property among rules whose selector
// matches a filter. Usage: node cascade.js <css> <property> <substr> [substr...]
// A selector is considered only if it contains every substring given.
const fs = require('fs');
const css = fs.readFileSync(process.argv[2], 'utf8');
const prop = process.argv[3];
const needles = process.argv.slice(4);

function specificity(sel) {
  let s = sel.replace(/::[a-z-]+(\([^)]*\))?/g, ' ');
  const ids = (s.match(/#[\w-]+/g) || []).length;
  const cls =
    (s.match(/\.[\w-]+/g) || []).length +
    (s.match(/\[[^\]]*\]/g) || []).length +
    (s.match(/:(?!:)[a-z-]+(\([^)]*\))?/gi) || []).length;
  s = s.replace(/#[\w-]+|\.[\w-]+|\[[^\]]*\]|:(?!:)[a-z-]+(\([^)]*\))?/gi, ' ');
  const el = (s.match(/(^|[\s>+~(,])([a-z][\w-]*)/gi) || []).length;
  return [ids, cls, el];
}

// Flat parse; good enough for compiled, already-flattened output.
const rules = [];
let idx = 0;
const re = /([^{}@]+)\{([^{}]*)\}/g;
let m;
while ((m = re.exec(css)) !== null) {
  const selectorList = m[1].trim();
  const body = m[2];
  if (!selectorList || selectorList.startsWith('@')) continue;
  const line = css.slice(0, m.index).split('\n').length;
  for (const sel of selectorList.split(',').map((x) => x.trim())) {
    if (!needles.every((n) => sel.includes(n))) continue;
    const decls = [...body.matchAll(/([-a-z]+)\s*:\s*([^;]+);?/gi)];
    for (const d of decls) {
      if (d[1].trim() !== prop) continue;
      const val = d[2].trim();
      rules.push({
        order: idx++,
        line,
        sel,
        spec: specificity(sel),
        val: val.replace(/\s*!important$/, ''),
        important: /!important$/.test(val),
      });
    }
  }
}

if (!rules.length) {
  console.log('no rule sets "' + prop + '" for selectors containing ' + JSON.stringify(needles));
  process.exit(0);
}

const key = (r) => [r.important ? 1 : 0, ...r.spec, r.order];
const cmp = (a, b) => {
  const ka = key(a), kb = key(b);
  for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i];
  return 0;
};
const sorted = [...rules].sort(cmp);
for (const r of rules) {
  console.log(
    '  L' + String(r.line).padEnd(6) +
    '(' + r.spec.join(',') + ')' + (r.important ? '!' : ' ') + '  ' +
    r.sel.slice(0, 62).padEnd(64) + prop + ': ' + r.val
  );
}
const w = sorted[sorted.length - 1];
console.log('  WINNER -> ' + prop + ': ' + w.val + (w.important ? ' !important' : '') + '   [L' + w.line + ' ' + w.sel + ']');
