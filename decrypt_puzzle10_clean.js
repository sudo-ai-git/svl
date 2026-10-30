// Puzzle Weave 10 - clean focused attempt
const fs = require('fs');
const document = {
    getElementById: function() { return { innerHTML: '', style: {} }; },
    getElementsByClassName: function() { return [{ onclick: null }]; },
    createElement: function() { return { setAttribute: function() {}, click: function() {}, style: {} }; },
    body: { appendChild: function() {}, removeChild: function() {} }
};
const cryptojsCode = fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs_clean.js', 'utf8');
eval(cryptojsCode);
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt', 'utf8').trim();

function hex2a(hexx) {
    var hex = hexx.toString();
    var str = '';
    for (var i = 0; i < hex.length; i += 2)
        str += String.fromCharCode(parseInt(hex.substr(i, 2), 16));
    return str;
}

function decodewallet(t, e) {
    for (var i = CryptoJS.SHA512(e), n = 0; n < 11512; n++) i = CryptoJS.SHA512(i);
    CryptoJS.algo.AES.keySize = 32;
    CryptoJS.algo.EvpKDF.cfg.iterations = 1e4;
    CryptoJS.algo.EvpKDF.cfg.keySize = 32;
    var r = CryptoJS.AES.decrypt(t, i.toString());
    return out = hex2a(r), out;
}

// Focused password list based on the 5 puzzle keys
const passwords = [
    // Key combinations: dice(1,2,4) + ICO(6,3,18) + order66 + genesis#28
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    // Without genesis
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    "124631866",
    // Genesis only
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    "wellseewhathappens",
    // Other combinations
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens",
];

console.log("Testing " + passwords.length + " passwords...");
let found = false;
for (const pwd of passwords) {
    try {
        const result = decodewallet(msg, pwd);
        if (result && result.indexOf('"kty":"RSA"') > -1) {
            console.log("\n*** FOUND PASSWORD: " + pwd + " ***");
            console.log("Decrypted: " + result.substring(0, 500));
            found = true;
            break;
        }
    } catch (e) {}
}
if (!found) console.log("No password found");
