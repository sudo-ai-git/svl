// Puzzle Weave 10 - focused decryption attempt
// Based on the 5 keys from PZL10 README:
// 1. Dice: 1, 2, 4 (win numbers 1 and 4)
// 2. ICO date: 6, 3, 18 (2018/06/03)
// 3. Order 66
// 4. [0-19] → 20 chars
// 5. Genesis #28: "We'll see what happens"

const fs = require('fs');

// Minimal DOM shim
const document = {
    getElementById: function() { return { innerHTML: '', style: {} }; },
    getElementsByClassName: function() { return [{ onclick: null }]; },
    createElement: function() { return { setAttribute: function() {}, click: function() {}, style: {} }; },
    body: { appendChild: function() {}, removeChild: function() {} }
};

// Read the CryptoJS library
const cryptojsCode = fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs_clean.js', 'utf8');
eval(cryptojsCode);

// Read the encrypted message
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt', 'utf8').trim();

// The hex2a function (from the puzzle)
function hex2a(hexx) {
    var hex = hexx.toString();
    var str = '';
    for (var i = 0; i < hex.length; i += 2)
        str += String.fromCharCode(parseInt(hex.substr(i, 2), 16));
    return str;
}

// The decodewallet function from the puzzle
function decodewallet(t, e) {
    for (var i = CryptoJS.SHA512(e), n = 0; n < 11512; n++) i = CryptoJS.SHA512(i);
    CryptoJS.algo.AES.keySize = 32;
    CryptoJS.algo.EvpKDF.cfg.iterations = 1e4;
    CryptoJS.algo.EvpKDF.cfg.keySize = 32;
    var r = CryptoJS.AES.decrypt(t, i.toString());
    return out = hex2a(r), out;
}

// Generate password candidates based on the 5 keys
const passwords = new Set();

// Key 1: Dice numbers (1, 2, 4) - various orderings and subsets
const key1 = ["1", "2", "4", "12", "14", "21", "24", "41", "42", "124", "142", "214", "241", "412", "421"];

// Key 2: ICO date (6, 3, 18) - various orderings
const key2 = ["6", "3", "18", "63", "36", "6318", "1863", "180603", "20180603", "630", "063", "0603"];

// Key 3: Order 66
const key3 = ["66", "order66", "order 66", "executeorder66", "execute order 66"];

// Key 5: Genesis #28 - "We'll see what happens"
const key5 = [
    "wellseewhathappens",
    "We'll see what happens",
    "we'll see what happens",
    "WELLSEEWHATHAPPENS",
    "well see what happens",
    "Well See What Happens",
];

// Generate combinations of keys 1, 2, 3
for (const k1 of key1) {
    for (const k2 of key2) {
        for (const k3 of key3) {
            passwords.add(k1 + k2 + k3);
            passwords.add(k1 + k2 + "66");
            passwords.add(k1 + k2);
            passwords.add(k2 + k1 + k3);
            passwords.add(k2 + k1);
            passwords.add(k1 + k2 + "66" + k3);
            passwords.add(k3 + k2 + k1);
            passwords.add(k2 + k1 + k3);
            passwords.add(k1 + k3 + k2);
            passwords.add(k3 + k1 + k2);
            passwords.add(k2 + k3 + k1);
        }
    }
}

// Add key5 combinations
for (const k5 of key5) {
    passwords.add(k5);
    for (const k1 of key1) {
        passwords.add(k1 + k5);
        passwords.add(k5 + k1);
        for (const k2 of key2) {
            passwords.add(k1 + k2 + k5);
            passwords.add(k5 + k1 + k2);
            passwords.add(k1 + k5 + k2);
            passwords.add(k2 + k1 + k5);
        }
    }
}

// Add specific combinations mentioned in the README
passwords.add("124631866");
passwords.add("214631866");
passwords.add("241631866");
passwords.add("412631866");
passwords.add("421631866");
passwords.add("142631866");
passwords.add("124631866wellseewhathappens");
passwords.add("wellseewhathappens124631866");

// Add some more combinations with different orderings
for (const k1 of key1) {
    for (const k2 of key2) {
        passwords.add(k1 + k2 + "66");
        passwords.add("66" + k1 + k2);
        passwords.add(k1 + "66" + k2);
        passwords.add(k2 + "66" + k1);
    }
}

// Convert to array and test
const passwordArray = Array.from(passwords);
console.log("Testing " + passwordArray.length + " password candidates...");

let found = false;
for (const pwd of passwordArray) {
    try {
        const result = decodewallet(msg, pwd);
        if (result && result.indexOf('"kty":"RSA"') > -1) {
            console.log("\n*** FOUND PASSWORD: " + pwd + " ***");
            console.log("Decrypted: " + result.substring(0, 500));
            found = true;
            break;
        }
    } catch (e) {
        // ignore errors
    }
}
if (!found) {
    console.log("No password found in the list");
}
