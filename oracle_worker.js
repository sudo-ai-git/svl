const fs = require('fs');
const crypto = require('crypto');
global.document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}}, getElementById: ()=>({value:'',innerHTML:'',style:{}}), getElementsByClassName: ()=>[{onclick:null}] };
global.window = {};
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl10_cjs.js','utf8'));
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;
function sha512chain(pw){
  let h = crypto.createHash('sha512').update(pw, 'utf8').digest();
  for (let n=0; n<11512; n++) h = crypto.createHash('sha512').update(h).digest();
  return h.toString('hex');
}
// Reads candidates (one per line) from file, checks each, prints MATCH lines.
const lines = fs.readFileSync(process.argv[2],'utf8').split('\n');
let hits = 0;
for (const line of lines){
  if (!line) continue;
  try {
    const key = sha512chain(line);
    const out = hex2a(CryptoJS.AES.decrypt(msg, key));
    if (out.indexOf('"kty":"RSA"') > -1){ console.log("MATCH: "+line); hits++; }
  } catch(e){}
}
console.log("DONE hits="+hits);
