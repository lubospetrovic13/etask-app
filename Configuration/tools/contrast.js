// WCAG contrast audit of the --app-* foreground tokens against their surfaces,
// read straight out of the compiled stylesheet. Usage: node contrast.js <css>
const fs = require('fs');
const css = fs.readFileSync(process.argv[2], 'utf8');

function blockAfter(selector) {
  const i = css.indexOf(selector + ' {');
  if (i === -1) return null;
  const start = css.indexOf('{', i) + 1;
  const end = css.indexOf('}', start);
  return css.slice(start, end);
}

function tokens(block) {
  const out = {};
  for (const m of block.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

function parse(color) {
  color = color.trim();
  let m = color.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  m = color.match(/^#([0-9a-f]{3})$/i);
  if (m) return m[1].split('').map((c) => parseInt(c + c, 16)).concat([1]);
  m = color.match(/^rgba?\(([^)]+)\)$/i);
  if (m) {
    const p = m[1].split(',').map((x) => parseFloat(x));
    return [p[0], p[1], p[2], p[3] === undefined ? 1 : p[3]];
  }
  return null;
}

const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);

function ratio(fg, bg) {
  const f = parse(fg), b = parse(bg);
  if (!f || !b) return null;
  const comp = [0, 1, 2].map((i) => f[i] * f[3] + b[i] * (1 - f[3]));
  const l1 = lum(comp), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

const modes = {light: tokens(blockAfter(':root')), dark: tokens(blockAfter('.app-dark'))};
const pairs = [
  ['--app-fg', '--app-bg'], ['--app-fg', '--app-surface'],
  ['--app-fg-muted', '--app-bg'], ['--app-fg-muted', '--app-surface'],
  ['--app-fg-faint', '--app-surface'],
  ['--app-fg-disabled', '--app-surface'],
  ['--app-accent', '--app-surface'],
  ['--app-success', '--app-surface'], ['--app-danger', '--app-surface'],
  ['--app-warning', '--app-surface'], ['--app-info', '--app-surface'],
  ['--app-fg', '--app-drawer'], ['--app-fg-muted', '--app-drawer'],
  ['--app-fg-muted', '--app-rail'],
  ['--app-chrome-fg', '--app-chrome'],
  ['--app-tooltip-fg', '--app-tooltip'],
  ['--app-border-interactive', '--app-surface'],
  ['--app-fg-disabled', '--app-surface'],
];

let fails = 0;
for (const [mode, t] of Object.entries(modes)) {
  console.log('\n' + mode.toUpperCase());
  for (const [fg, bg] of pairs) {
    const r = ratio(t[fg], t[bg]);
    if (r === null) { console.log('  ?? ' + fg + ' on ' + bg + ' (unparsed)'); continue; }
    // 4.5:1 is AA for normal text; status colours are used as small text/dots too.
    // UI component boundaries need 3:1, not 4.5:1; 'faint' is placeholder weight.
    const bar = (fg === '--app-fg-faint' || fg === '--app-border-interactive') ? 3.0 : 4.5;
    const ok = r >= bar;
    if (!ok) fails++;
    console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + r.toFixed(2).padStart(6) + ':1  ' +
      fg.padEnd(20) + ' on ' + bg.padEnd(18) + t[fg] + ' / ' + t[bg]);
  }
}
console.log('\n' + (fails ? fails + ' pair(s) below 4.5:1' : 'all pairs >= 4.5:1'));
