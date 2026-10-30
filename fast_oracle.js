
const fs = require('fs');
const document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}} };
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs_clean.js','utf8'));
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize = 32, CryptoJS.algo.EvpKDF.cfg.iterations = 1e4, CryptoJS.algo.EvpKDF.cfg.keySize = 32;
function decodewallet(t,e){for(var i=CryptoJS.SHA512(e),n=0;n<11512;n++)i=CryptoJS.SHA512(i);var r=CryptoJS.AES.decrypt(t,i.toString());return hex2a(r)}
const lines = fs.readFileSync(process.argv[2],'utf8').split('\n');
let hits=0;
for(const line of lines){ if(!line) continue; try{ const o=decodewallet(msg,line); if(o.indexOf('"kty":"RSA"')>-1){console.log("MATCH: "+line); hits++;} }catch(e){} }
console.log("DONE hits="+hits);
