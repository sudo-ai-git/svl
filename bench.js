
const fs=require('fs'), crypto=require('crypto');
global.document={createElement:()=>({setAttribute(){},click(){},style:{}}),body:{appendChild(){},removeChild(){}},getElementById:()=>({value:'',innerHTML:'',style:{}}),getElementsByClassName:()=>[{onclick:null}]};
global.window={};
eval(fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl10_cjs.js','utf8'));
const msg=fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt','utf8').trim();
function hex2a(t){for(var e=t.toString(),i="",n=0;n<e.length&&"00"!==e.substr(n,2);n+=2)i+=String.fromCharCode(parseInt(e.substr(n,2),16));return i}
CryptoJS.algo.AES.keySize=32,CryptoJS.algo.EvpKDF.cfg.iterations=1e4,CryptoJS.algo.EvpKDF.cfg.keySize=32;
function sha512chain(pw){let h=crypto.createHash('sha512').update(pw,'utf8').digest();for(let n=0;n<11512;n++)h=crypto.createHash('sha512').update(h).digest();return h.toString('hex');}
let t=Date.now(); for(let i=0;i<50;i++) sha512chain("cand"+i); console.log("50 sha chains ms:", Date.now()-t);
const key=sha512chain("x"); t=Date.now(); for(let i=0;i<50;i++){hex2a(CryptoJS.AES.decrypt(msg,key));} console.log("50 AES ms:", Date.now()-t);
