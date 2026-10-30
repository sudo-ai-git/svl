const fs = require('fs');
const crypto = require('crypto');
global.document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}}, getElementById: ()=>({value:'',innerHTML:'',style:{}}), getElementsByClassName: ()=>[{onclick:null}] };
global.window = {};
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl10_cjs.js','utf8'));
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;
function sha512chain(pw){
  let h = crypto.createHash('sha512').update(pw, 'utf8').digest();
  for (let n=0; n<11512; n++) h = crypto.createHash('sha512').update(h).digest();
  return h.toString('hex');
}
// PZL8 solved vector
const p8msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl8_msg.txt','utf8').trim();
const p8ans = "RasputinWilhelmAlekhine";
const key = sha512chain(p8ans);
const out = hex2a(CryptoJS.AES.decrypt(p8msg, key));
console.log("PZL8 out head:", JSON.stringify(out.slice(0, 60)));
console.log("PZL8 gate present:", out.indexOf('"kty":"RSA"') > -1);
// derive address
try {
  const jwk = JSON.parse(out);
  const n = jwk.n;
  // base64url decode n (Arweave JWK uses standard base64 for n)
  const buf = Buffer.from(n, 'base64');
  const addr = crypto.createHash('sha256').update(buf).digest('base64').replace(/\+/g,'-').replace(/\//g,'_');
  console.log("derived address:", addr);
  console.log("expected       : ayJQH1S6Fi52OEokLVi2tl5kr_y39LSfhJcNV0z9Ny4");
  console.log("ADDRESS MATCH:", addr === "ayJQH1S6Fi52OEokLVi2tl5kr_y39LSfhJcNV0z9Ny4");
} catch(e){ console.log("jwk err:", e.message); }
