const fs = require('fs');
const crypto = require('crypto');
// DOM shim
global.document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}}, getElementById: ()=>({value:'',innerHTML:'',style:{}}), getElementsByClassName: ()=>[{onclick:null}] };
global.window = {};
// Load page CryptoJS (script 0: defines CryptoJS incl SHA512/AES/EvpKDF)
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl10_cjs.js','utf8'));

const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;

// Fast sha512 x11513 chain using NATIVE crypto, returns hex string (same as CryptoJS i.toString())
function sha512chain(pw){
  let h = crypto.createHash('sha512').update(pw, 'utf8').digest();
  for (let n=0; n<11512; n++) h = crypto.createHash('sha512').update(h).digest();
  return h.toString('hex');
}

// Validate: native chain digest must equal CryptoJS chain digest for same pw
(function validate(){
  var i = CryptoJS.SHA512("testpw");
  for (var n=0;n<11512;n++) i = CryptoJS.SHA512(i);
  const cjsHex = i.toString();
  const nativeHex = sha512chain("testpw");
  console.log("CryptoJS:", cjsHex.slice(0,32));
  console.log("native  :", nativeHex.slice(0,32));
  console.log("MATCH:", cjsHex === nativeHex);
})();

const lines = fs.readFileSync(process.argv[2],'utf8').split('\n');
const t0 = Date.now();
let hits = 0;
for (const line of lines){
  if (!line) continue;
  try {
    const key = sha512chain(line);
    const r = CryptoJS.AES.decrypt(msg, key);
    const out = hex2a(r);
    if (out.indexOf('"kty":"RSA"') > -1){ console.log("MATCH: "+line); hits++; }
  } catch(e){}
}
console.log("DONE hits="+hits+" time_ms="+(Date.now()-t0));
