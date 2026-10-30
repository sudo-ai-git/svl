
const fs = require('fs');
const document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}} };
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs_clean.js','utf8'));
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;
// args are already-sha512'd hex strings
for (let k=2;k<process.argv.length;k++){
  try{ const r = CryptoJS.AES.decrypt(msg, process.argv[k]); const out = hex2a(r);
    if(out.slice(0,60).search('"kty":"RSA"')>-1) console.log("HIT:"+process.argv[k]);
  }catch(e){}
}
console.log("DONE");
