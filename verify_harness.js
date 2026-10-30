
const fs = require('fs');
const document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}} };
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs_clean.js','utf8'));
console.log("CryptoJS defined:", typeof CryptoJS !== 'undefined');
console.log("SHA512 defined:", typeof CryptoJS.SHA512);
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
console.log("msg len:", msg.length);
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;
const t0 = Date.now();
var i = CryptoJS.SHA512("testpw");
for(var n=0;n<11512;n++) i = CryptoJS.SHA512(i);
console.log("hash chain ms:", Date.now()-t0);
const t1 = Date.now();
var r = CryptoJS.AES.decrypt(msg, i.toString());
const out = hex2a(r);
console.log("decrypt ms:", Date.now()-t1, "outlen:", out.length, "outhead:", out.slice(0,40));
