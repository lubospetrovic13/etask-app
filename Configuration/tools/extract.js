const fs=require('fs'),path=require('path');
const roots=process.argv.slice(2,-1), out=process.argv[process.argv.length-1];
let n=0;
function walk(d,cb){for(const e of fs.readdirSync(d,{withFileTypes:true})){const p=path.join(d,e.name);if(e.isDirectory())walk(p,cb);else cb(p);}}
for(const root of roots){
  walk(root,p=>{
    if(!p.endsWith('.mjs'))return;
    const txt=fs.readFileSync(p,'utf8');
    const m=txt.match(/sourceMappingURL=data:application\/json;base64,([A-Za-z0-9+/=]+)/);
    if(!m)return;
    let map;try{map=JSON.parse(Buffer.from(m[1],'base64').toString('utf8'));}catch(e){return;}
    if(!map.sourcesContent)return;
    map.sources.forEach((s,i)=>{
      const c=map.sourcesContent[i]; if(c==null)return;
      let rel=s.replace(/^(\.\.\/)+/,'');
      const dest=path.join(out,rel);
      fs.mkdirSync(path.dirname(dest),{recursive:true});
      fs.writeFileSync(dest,c); n++;
    });
  });
}
console.log('wrote',n,'files');
