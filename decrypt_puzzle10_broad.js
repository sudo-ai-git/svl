// Puzzle Weave 10 - broader search with systematic combinations
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

// The 5 keys from PZL10 README:
// 1. Dice: shows 1, 2, 4 (win numbers 1 and 4)
// 2. ICO date: 6, 3, 18 (2018/06/03)
// 3. Order 66: 66 (also = 66M AR max supply)
// 4. [0-19]: 20 characters
// 5. Genesis #28: "We'll see what happens"

// The password is likely a specific combination. Let me try many variations.

const passwords = new Set();

// Key 1 variations (dice)
const dice = ["1", "2", "4", "12", "14", "21", "24", "41", "42", "124", "142", "214", "241", "412", "421"];

// Key 2 variations (ICO date)
const ico = ["6", "3", "18", "63", "36", "6318", "1863", "180603", "20180603", "630", "063", "0603"];

// Key 3 variations (order 66)
const order = ["66", "order66", "order 66", "executeorder66", "execute order 66"];

// Key 5 variations (genesis #28)
const genesis = [
    "wellseewhathappens",
    "We'll see what happens",
    "we'll see what happens",
    "WELLSEEWHATHAPPENS",
    "well see what happens",
    "Well See What Happens",
];

// Generate all combinations of dice + ico + order
for (const d of dice) {
    for (const i of ico) {
        for (const o of order) {
            passwords.add(d + i + o);
            passwords.add(d + i + "66");
            passwords.add(d + i);
            passwords.add(i + d + o);
            passwords.add(i + d);
            passwords.add(d + "66" + i);
            passwords.add("66" + d + i);
            passwords.add(i + "66" + d);
            passwords.add(d + o + i);
            passwords.add(o + d + i);
            passwords.add(i + o + d);
            passwords.add(o + i + d);
        }
    }
}

// Add genesis combinations
for (const g of genesis) {
    passwords.add(g);
    for (const d of dice) {
        passwords.add(d + g);
        passwords.add(g + d);
        for (const i of ico) {
            passwords.add(d + i + g);
            passwords.add(g + d + i);
            passwords.add(d + g + i);
            passwords.add(i + d + g);
            passwords.add(g + i + d);
            passwords.add(i + g + d);
        }
    }
}

// Add 20-character slices of longer combinations
const longer = [];
for (const d of dice) {
    for (const i of ico) {
        for (const g of genesis) {
            longer.push(d + i + "66" + g);
            longer.push(d + i + g);
            longer.push(g + d + i + "66");
        }
    }
}

for (const s of longer) {
    if (s.length >= 20) {
        passwords.add(s.substring(0, 20));
        passwords.add(s.substring(s.length - 20));
    }
    passwords.add(s);
}

// Add some specific 20-char candidates
passwords.add("124631866wellseewha");  // 20 chars
passwords.add("124631866wellseewhat"); // 21 chars
passwords.add("124631866wellseewhath"); // 22 chars
passwords.add("124631866wellseewhathappens"); // 26 chars
passwords.add("20wellseewhathappens"); // 20 chars
passwords.add("wellseewhathappens20"); // 20 chars
passwords.add("wellseewhathappens66"); // 20 chars
passwords.add("wellseewhathappens124"); // 20 chars
passwords.add("wellseewhathappens6318"); // 21 chars
passwords.add("wellseewhathappens1246"); // 21 chars
passwords.add("wellseewhathappens12463"); // 22 chars
passwords.add("wellseewhathappens124631"); // 23 chars
passwords.add("wellseewhathappens1246318"); // 24 chars
passwords.add("wellseewhathappens12463186"); // 25 chars
passwords.add("wellseewhathappens124631866"); // 26 chars

// Add more variations with spaces and special chars
passwords.add("124 6318 66");
passwords.add("124-6318-66");
passwords.add("124.6318.66");
passwords.add("124_6318_66");
passwords.add("124631866 wellseewhathappens");
passwords.add("wellseewhathappens 124631866");
passwords.add("124631866_wellseewhathappens");
passwords.add("wellseewhathappens_124631866");

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
    } catch (e) {}
}
if (!found) console.log("No password found in the list");
