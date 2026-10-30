// Puzzle Weave 10 - comprehensive search with 20-char and 24-char focus
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

// Key components
const key1Parts = ["124", "142", "214", "241", "412", "421", "12", "14", "21", "24", "41", "42", "1", "2", "4", "21424", "2414", "12424"];
const key2Parts = ["6318", "630", "063", "63", "36", "63018", "180603", "20180603", "1863", "63180", "63182018"];
const key3Parts = ["66", "order66", "order 66", "a66", "66a", "executeorder66", "execute order 66"];
const key5Parts = ["wellseewhathappens", "We'll see what happens", "we'll see what happens", "WELLSEEWHATHAPPENS", "well see what happens", "Well See What Happens"];

const allPasswords = new Set();

// Generate all permutations of key1, key2, key3 (without key5)
const separators = ["", "_", "-", " ", ".", "@", "#"];

for (const k1 of key1Parts) {
    for (const k2 of key2Parts) {
        for (const k3 of key3Parts) {
            const parts = [k1, k2, k3];
            const perms = [
                [0,1,2], [0,2,1], [1,0,2], [1,2,0], [2,0,1], [2,1,0]
            ];
            for (const sep of separators) {
                for (const perm of perms) {
                    const combined = parts[perm[0]] + sep + parts[perm[1]] + sep + parts[perm[2]];
                    allPasswords.add(combined);
                    if (combined.length >= 20) allPasswords.add(combined.substring(0, 20));
                    if (combined.length >= 24) allPasswords.add(combined.substring(0, 24));
                }
            }
        }
    }
}

// Generate all permutations of key1, key2, key3, key5 (with key5)
for (const k1 of key1Parts) {
    for (const k2 of key2Parts) {
        for (const k3 of key3Parts) {
            for (const k5 of key5Parts) {
                const parts = [k1, k2, k3, k5];
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
                        if (combined.length >= 20) allPasswords.add(combined.substring(0, 20));
                        if (combined.length >= 24) allPasswords.add(combined.substring(0, 24));
                    }
                }
            }
        }
    }
}

// Add specific 20-char and 24-char strings
const specificStrings = [
    "01234567890123456789",
    "0123456789012345678",
    "1246318660123456789",
    "12463186601234567890",
    "12463186600000000000",
    "124631866000000000000",
    "1246318660000000000000",
    "124631866wellseewhatha",
    "124631866wellseewhathapp",
    "124631866wellseewhathappe",
    "124631866wellseewhathappen",
    "124631866wellseewhathappens",
    "wellseewhathappens1246318",
    "wellseewhathappens12463186",
    "wellseewhathappens124631866",
    "wellseewhathappe124631866",
    "wellseewhathappen124631866",
    "wellseewhathappens12463186",
    "124631866awellseewhathapp",
    "124631866awellseewhathappe",
    "124631866awellseewhathappen",
    "124631866awellseewhathappens",
    "12463186612463186612463186",
    "1246318661246318661246318",
    "124631866124631866124631",
    "12463186612463186612463",
    "1246318661246318661246",
    "124631866124631866124",
    "12463186612463186612",
    "1246318661246318661",
    "124631866124631866",
    "12463186612463186",
    "1246318661246318",
    "124631866124631",
    "12463186612463",
    "1246318661246",
    "124631866124",
    "12463186612",
    "1246318661",
    "124631866",
    "12463186",
    "1246318",
    "124631",
    "12463",
    "1246",
    "124",
    "12",
    "1"
];

for (const s of specificStrings) {
    allPasswords.add(s);
}

// Add padded versions
for (const k1 of key1Parts) {
    for (const k2 of key2Parts) {
        for (const k3 of key3Parts) {
            const combined = k1 + k2 + k3;
            // Pad with zeros to 20 chars
            if (combined.length < 20) {
                allPasswords.add(combined + "0".repeat(20 - combined.length));
            }
            // Pad with spaces to 20 chars
            if (combined.length < 20) {
                allPasswords.add(combined + " ".repeat(20 - combined.length));
            }
            // Pad with zeros to 24 chars
            if (combined.length < 24) {
                allPasswords.add(combined + "0".repeat(24 - combined.length));
            }
            // Pad with spaces to 24 chars
            if (combined.length < 24) {
                allPasswords.add(combined + " ".repeat(24 - combined.length));
            }
        }
    }
}

// Add repeated versions
for (const k1 of key1Parts) {
    for (const k2 of key2Parts) {
        for (const k3 of key3Parts) {
            const combined = k1 + k2 + k3;
            // Repeat to 20 chars
            let repeated = "";
            while (repeated.length < 20) {
                repeated += combined;
            }
            allPasswords.add(repeated.substring(0, 20));
            // Repeat to 24 chars
            repeated = "";
            while (repeated.length < 24) {
                repeated += combined;
            }
            allPasswords.add(repeated.substring(0, 24));
        }
    }
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
