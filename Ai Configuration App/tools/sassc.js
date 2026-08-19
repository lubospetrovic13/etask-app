// Compiles a project SCSS entry the way Angular CLI does (loadPaths + '~' importer).
const path = require('path'), fs = require('fs'), url = require('url');
const {createRequire} = require('module');
// Frontend repo root. Override when the repos move (e.g. into one monorepo):
//   FE_ROOT=C:/path/to/frontend node tools/sassc.js <entry.scss> [out.css]
const ROOT = process.env.FE_ROOT || 'C:/Users/petro/WebstormProjects/etask-frontend-starter';
const sass = createRequire(path.join(ROOT, 'package.json'))('sass');
const entry = process.argv[2], out = process.argv[3];

const tildeImporter = {
  findFileUrl(u) {
    if (!u.startsWith('~')) return null;
    let p = u.slice(1);
    if (p.startsWith('node_modules/')) p = p.slice('node_modules/'.length);
    return url.pathToFileURL(path.join(ROOT, 'node_modules', p));
  }
};

try {
  const res = sass.compile(entry, {
    loadPaths: [ROOT, path.join(ROOT, 'node_modules'), path.dirname(entry)],
    importers: [tildeImporter],
    quietDeps: true,
    logger: {warn: () => {}},
  });
  if (out) fs.writeFileSync(out, res.css);
  console.log('OK  bytes=' + res.css.length);
} catch (e) {
  console.log('FAIL: ' + e.message.split('\n')[0]);
  if (e.span && e.span.url) console.log('  at ' + e.span.url.href.replace('file:///' + ROOT.replace(/\//g,'/') + '/','') + ':' + (e.span.start.line + 1));
  else console.log(e.message);
  process.exit(1);
}
