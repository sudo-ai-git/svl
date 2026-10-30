const fs = require('fs');
// DOM shim for the page's download() function
global.document = { createElement: ()=>({setAttribute(){},click(){},style:{}}), body:{appendChild(){},removeChild(){}}, getElementById: ()=>({value:'',innerHTML:'',style:{}}), getElementsByClassName: ()=>[{onclick:null}] };
global.window = {};
// Load the page's own CryptoJS + helpers (defines CryptoJS, SHA512, decodewallet, msg)
const pageCode = fs.readFileSync('/home/sudosudo/.openclaw/workspace/pzl10_full.js','utf8');
eval(pageCode);

console.log("SHA512 fn:", typeof CryptoJS.SHA512, "| msg len:", (typeof msg!=='undefined') ? msg.length : 'UNDEF');
const t0 = Date.now();
var i = CryptoJS.SHA512("testpw");
for (var n=0;n<11512;n++) i = CryptoJS.SHA512(i);
console.log("hash chain ms:", Date.now()-t0, "digest:", i.toString().slice(0,32));
const t1 = Date.now();
var out = decodewallet(msg, "testpw");
console.log("decodewallet ms:", Date.now()-t1, "outlen:", out.length, "head:", JSON.stringify(out.slice(0,30)));
