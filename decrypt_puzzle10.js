// Puzzle Weave 10 - decryption attempt
// Replicates the exact logic from the puzzle HTML

const fs = require('fs');

// Read the CryptoJS library
const cryptojsCode = fs.readFileSync('/home/sudosudo/.openclaw/workspace/cryptojs.js', 'utf8');
eval(cryptojsCode);

// Read the encrypted message
const msg = fs.readFileSync('/home/sudosudo/.openclaw/workspace/encrypted_msg.txt', 'utf8').trim();

// The decodewallet function from the puzzle
function decodewallet(t, e) {
    for (var i = CryptoJS.SHA512(e), n = 0; n < 11512; n++) i = CryptoJS.SHA512(i);
    CryptoJS.algo.AES.keySize = 32;
    CryptoJS.algo.EvpKDF.cfg.iterations = 1e4;
    CryptoJS.algo.EvpKDF.cfg.keySize = 32;
    var r = CryptoJS.AES.decrypt(t, i.toString());
    return out = hex2a(r), out;
}

// The hex2a function (from the puzzle)
function hex2a(hexx) {
    var hex = hexx.toString(); //force conversion
    var str = '';
    for (var i = 0; i < hex.length; i += 2)
        str += String.fromCharCode(parseInt(hex.substr(i, 2), 16));
    return str;
}

// Try various passwords
const passwords = [
    "8Ball10", "8ball10", "8BALL10",
    "8Ball", "8ball", "8BALL",
    "eightBall10", "EightBall10", "EIGHTBALL10",
    "eightball", "EightBall", "EIGHTBALL",
    "puzzle10", "Puzzle10", "PUZZLE10",
    "arweave10", "Arweave10", "ARWEAVE10",
    "weave10", "Weave10", "WEAVE10",
    "genesis10", "Genesis10", "GENESIS10",
    "block10", "Block10", "BLOCK10",
    "puzzle8ball", "Puzzle8Ball", "PUZZLE8BALL",
    "puzzle8ball10", "Puzzle8Ball10", "PUZZLE8BALL10",
    "arweave8ball", "Arweave8Ball", "ARWEAVE8BALL",
    "arweave8ball10", "Arweave8Ball10", "ARWEAVE8BALL10",
    "weave8ball", "Weave8Ball", "WEAVE8BALL",
    "weave8ball10", "Weave8Ball10", "WEAVE8BALL10",
    "genesis8ball", "Genesis8Ball", "GENESIS8BALL",
    "genesis8ball10", "Genesis8Ball10", "GENESIS8BALL10",
    "block8ball", "Block8Ball", "BLOCK8BALL",
    "block8ball10", "Block8Ball10", "BLOCK8BALL10",
    "puzzleweave8ball", "PuzzleWeave8Ball", "PUZZLEWEAVE8BALL",
    "puzzleweave8ball10", "PuzzleWeave8Ball10", "PUZZLEWEAVE8BALL10",
    "puzzleweave10", "PuzzleWeave10", "PUZZLEWEAVE10",
    "puzzleweave", "PuzzleWeave", "PUZZLEWEAVE",
    "puzzle", "Puzzle", "PUZZLE",
    "arweave", "Arweave", "ARWEAVE",
    "weave", "Weave", "WEAVE",
    "genesis", "Genesis", "GENESIS",
    "block", "Block", "BLOCK",
    "10", "ten", "Ten",
    "8ball", "8Ball", "8BALL",
    "eightball", "EightBall", "EIGHTBALL",
    "eight ball", "Eight Ball", "EIGHT BALL",
    "8 ball", "8 Ball", "8 BALL",
    "magic8ball", "Magic8Ball", "MAGIC8BALL",
    "magic 8 ball", "Magic 8 Ball", "MAGIC 8 BALL",
    "the8ball", "The8Ball", "THE8BALL",
    "the 8 ball", "The 8 Ball", "THE 8 BALL",
    "8-ball", "8-BALL", "EIGHT-BALL",
    "eight-ball", "Eight-Ball", "EIGHT-BALL",
    "magic-8-ball", "Magic-8-Ball", "MAGIC-8-BALL",
    "the-8-ball", "The-8-Ball", "THE-8-BALL",
    "8ball10", "8Ball10", "8BALL10",
    "eightball10", "EightBall10", "EIGHTBALL10",
    "puzzle8ball", "Puzzle8Ball", "PUZZLE8BALL",
    "puzzle 8 ball", "Puzzle 8 Ball", "PUZZLE 8 BALL",
    "arweave8ball", "Arweave8Ball", "ARWEAVE8BALL",
    "arweave 8 ball", "Arweave 8 Ball", "ARWEAVE 8 BALL",
    "weave8ball", "Weave8Ball", "WEAVE8BALL",
    "weave 8 ball", "Weave 8 Ball", "WEAVE 8 BALL",
    "genesis8ball", "Genesis8Ball", "GENESIS8BALL",
    "genesis 8 ball", "Genesis 8 Ball", "GENESIS 8 BALL",
    "block8ball", "Block8Ball", "BLOCK8BALL",
    "block 8 ball", "Block 8 Ball", "BLOCK 8 BALL",
    "puzzleweave8ball", "PuzzleWeave8Ball", "PUZZLEWEAVE8BALL",
    "puzzleweave 8 ball", "PuzzleWeave 8 Ball", "PUZZLEWEAVE 8 BALL",
];

let found = false;
for (const pwd of passwords) {
    try {
        const result = decodewallet(msg, pwd);
        if (result && result.indexOf('"kty":"RSA"') > -1) {
            console.log(`\n*** FOUND PASSWORD: ${pwd} ***`);
            console.log(`Decrypted: ${result.substring(0, 500)}`);
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
