// Puzzle Weave 10 - focused decryption attempt
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

// The 5 keys:
// 1. Dice: 1, 2, 4 (win numbers 1, 4) → "124"
// 2. ICO date: 6, 3, 18 → "6318" or "630" or "063"
// 3. Order 66: 66
// 4. [0-19]: slice to 20 characters
// 5. Genesis #28: "We'll see what happens" → "wellseewhathappens"

// Generate all permutations of the 4 base keys, then take first 20 chars
const key1 = ["124", "142", "214", "241", "412", "421", "12", "14", "21", "24", "41", "42", "1", "2", "4"];
const key2 = ["6318", "630", "063", "63", "36", "63018", "180603", "20180603", "1863", "63180"];
const key3 = ["66", "order66", "order 66"];
const key5 = ["wellseewhathappens", "We'll see what happens", "we'll see what happens"];

const allPasswords = new Set();

// All permutations of 4 keys (k1, k2, k3, k5) with all separators
const separators = ["", "_", "-", " ", ".", "@", "#"];

for (const k1 of key1) {
    for (const k2 of key2) {
        for (const k3 of key3) {
            for (const k5 of key5) {
                const parts = [k1, k2, k3, k5];
                // Generate all 24 permutations of 4 elements
                const perms = [
                    [0,1,2,3], [0,1,3,2], [0,2,1,3], [0,2,3,1], [0,3,1,2], [0,3,2,1],
                    [1,0,2,3], [1,0,3,2], [1,2,0,3], [1,2,3,0], [1,3,0,2], [1,3,2,0],
                    [2,0,1,3], [2,0,3,1], [2,1,0,3], [2,1,3,0], [2,3,0,1], [2,3,1,0],
                    [3,0,1,2], [3,0,2,1], [3,1,0,2], [3,1,2,0], [3,2,0,1], [3,2,1,0]
                ];
                for (const sep of separators) {
                    for (const perm of perms) {
                        const combined = parts[perm[0]] + sep + parts[perm[1]] + sep + parts[perm[2]] + sep + parts[perm[3]];
                        allPasswords.add(combined);
                        // [0-19] = first 20 characters
                        if (combined.length >= 20) {
                            allPasswords.add(combined.substring(0, 20));
                        }
                    }
                }
            }
        }
    }
}

// Also try without k5 (just k1+k2+k3), then slice to 20
for (const k1 of key1) {
    for (const k2 of key2) {
        for (const k3 of key3) {
            for (const sep of separators) {
                const combined = k1 + sep + k2 + sep + k3;
                allPasswords.add(combined);
                if (combined.length >= 20) {
                    allPasswords.add(combined.substring(0, 20));
                }
            }
        }
    }
}

// Also try just the 20-char string "01234567890123456789"
allPasswords.add("01234567890123456789");
allPasswords.add("0123456789012345678");

// Also try some specific 20-char combinations
const specific20 = [
    "124631866wellseewha",
    "124631866wellseewhat",
    "124631866wellseewhath",
    "124631866wellseewhatha",
    "124631866wellseewhathap",
    "124631866wellseewhathapp",
    "124631866wellseewhathappe",
    "124631866wellseewhathappen",
    "124631866wellseewhathappens",
    "124631866wellseewhathappens20",
    "20wellseewhathappens",
    "wellseewhathappens20",
    "wellseewhathappens66",
    "wellseewhathappens124",
    "wellseewhathappens6318",
    "wellseewhathappens1246",
    "wellseewhathappens12463",
    "wellseewhathappens124631",
    "wellseewhathappens1246318",
    "wellseewhathappens12463186",
    "wellseewhathappens124631866"
];
for (const s of specific20) {
    allPasswords.add(s);
}

const passwordArray = Array.from(allPasswords);
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
