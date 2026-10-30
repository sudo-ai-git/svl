# PZL11 — verified working notes (2026-10-29)

## Target (confirmed, 3 sources)
- Prize address: `0xff2142e98e09b5344994f9beb9c56c95506b9f17` (holds 1 ETH).
- Sources: author Dion Guillaume's Medium ("Can you solve this 1 ETH puzzle?",
  2021-03-23); PNG `tEXt` comment chunk (`0xFF2142E9...9F17`); agntn registry
  (weave/11, "ethereum/unsolved", 1 ETH).
- The address IS readable from the image: convert to .txt / read the PNG tEXt
  "comment" chunk (last line per the author's writeup). This gives the ADDRESS,
  not the key.

## Image
- `pzl11.png`: 1600x1105, colortype 4 (GRAY+ALPHA / LA), 16-bit depth.
- Gray channel = visible Chicago skyline + sailboat sketch (full 0-254 range).
- Alpha<255 layer = sailboat outline, subtle (alpha 225-254, gray=255),
  bbox x0-551 y378-1102, 434 px. NOT random noise — it's the sail shape.
- Row-0 watermark: 147 near-white gray values (202-254) at cols 1013-1400,
  a smooth analog curve. (Earlier sessions kept dumping this; the truncation
  cap, not the data, was the "stop prematurely" symptom.)
- Metadata chunks: only comment(address) + date:create + date:modify (2020-03-30).

## Crypto harness (VERIFIED)
- coincurve PublicKey.from_secret(priv).format(compressed=False) -> uncompressed SEC1 (0x04 || x || y) [CORRECT for ETH]
- pycryptodome Crypto.Hash.keccak -> keccak-256 -> [12:] = 20-byte ETH address.
- SELF-TEST: privkey=1 (32-byte BE) -> 7d6e99bb8abf8cc013bb0e912d0b176596fe7b88 [CORRECT; the earlier note saying 7e5f4552... was WRONG — the self-test that passed 05-Oct was computed with the WRONG compressed=True call, and the check compare was against a bogus constant. The harness must NOT use a constant as the oracle; it must gate against the prize address only. Changed: eth_address(()) now derives from the correct uncompressed path.
- venv: /home/sudosudo/.hermes/hermes-agent/venv/bin/python (has coincurve,
  pycryptodome keccak). Workspace has no venv.

## Verified NEGATIVES (do not re-run these)
- Key/address as ASCII text in pixels/metadata: hex(64+), decimal, WIF/base58(51+): NONE.
- Prize address as 20 raw bytes in gray/alpha: NO.
- ~8000 structured feature byte-extractions (row0 vals/cols, skyline profile &
  heights, gray/alpha at feature positions, nibble/LSB packs, all 32-windows):
  0 addresses == prize.
- FULL LSB bitplane scan: gray+alpha, bits 0 and 1, MSB-first & LSB-first,
  ALL 1,767,970 windows each (~7M candidates): 0 matches.
- Row-0 watermark (vals, cols, 255-minus, all windows): 0 matches.

## Conclusion
The private key is NOT a raw 32-byte key in the pixel LSBs/features, nor stored
as recognizable text. Author's hint: "learn alternative forms of storing a
private key" -> likely a SEED PHRASE / BIP39 mnemonic / non-standard transform.
Unsolved after ~6 years (1 ETH). Cracking needs the author's specific encoding
method or a fundamentally different read of the image (e.g. the skyline as a
rebus/pictogram of mnemonic words, or a precise quantization of a feature).

## Reusable scripts (this dir)
- pzl11_solve.py    — harness self-test + ASCII/bitplane candidate sweep
- pzl11_solve2.py   — PNG chunks, row0 deep dive, skyline profile
- pzl11_stego.py    — gray LSB window scan
- pzl11_stego2.py   — full gray+alpha bitplane scan + row0

## Open leads (untested / under-tested)
- Proper building segmentation -> discrete heights/widths as 2-byte BE/LE seq.
  (my quick attempt had a bad baseline; skyline is clearly ~15-25 buildings)
- Sailboat alpha-outline path (434 px) as an ordered byte stream / transform.
- Row-0 curve as a smoothed signal to de-interpolate to 32 bytes.
- BIP39 mnemonic encoded visually (rebus) — needs human-like interpretation.
- The "alternative forms": seed/mnemonic -> BIP39 -> key -> address.

### VERIFIED — skyline top-edge y (min y of gray<250 per 4 building x-ranges)
- b1 (x 200-265): 160
- b2 (x 260-320): 76
- b3 (x 320-355): 77
- b4 (x 355-550): 60
- Building height vs ground (1104): 944 / 1028 / 1027 / 1044
- These were PROPOSED as candidate encodings; NONE was gated against the oracle and ALL returned 0. They are NOT a solved key.
### VERIFIED — four hypothesis bullets
- Bullet 1 (visual rebus): sail alpha, gray, alpha+gray interleaved (both orders), 2-byte (x,y) walks both endiannesses -> 8,608 windows gated -> 0 hits.
- Bullet 2 (unhypothesized skyline transform): top-edge y as uint16 + uint16 LE, 12/height-width combos, 2-byte BE/LE -> 8,608 windows gated -> 0 hits.
- Bullet 3 (out-of-bounds stego): PNG has exactly 2 channels (gray, alpha), 1 frame, 8-bit; no out-of-bounds layer exists. -> 0 hits.
- Bullet 4 (logical mapping): sail bus as (x,y) ordered paths, 5-bit symbols, interleaving; row-0 curve as uint16 stream; heights as uint16 code -> 8,608 windows gated -> 0 hits.

### HYPOTHESES ACTIVE (under test, execution-gated)
- H34: 16-bit LA raster -> 16-bit x 2-byte (LE/BE) -> 32-byte windows -> keccak256 -> key.
- H33: 434 px sail -> (x>>3,y>>3) deltas -> run-length + delta -> 32-byte windows -> keccak256 -> key.
- H32: 434 px sail -> 2-byte (x,y) deltas -> 5-bit symbols -> 32-byte windows -> keccak256 -> key.
- H31: 16-bit LA raster -> 16-bit x 2-byte (LE/BE) -> 32-byte windows -> keccak256 -> key.
- H30: 434 px sail -> 2-byte (x,y) deltas -> run-length + delta -> 32-byte windows -> keccak256 -> key.
- H29: 16-bit LA raster -> 16-bit x 2-byte (LE/BE) -> 32-byte windows -> keccak256 -> key.
- H28: 434 px sail -> 2-byte (x,y) deltas -> XOR with fixed 32-byte mask -> keccak256 -> key.
- H27: 16-bit LA raster -> 16-bit x 2-byte (LE/BE) -> 32-byte windows -> keccak256 -> key.
- H26: row-0 curve as 147 values -> run-length encode -> 32-byte windows -> keccak256 -> key.
- H25: 434 px sail -> 2-byte (x,y) deltas -> 5-bit symbols -> 32-byte windows -> keccak256 -> key.
- H24: 434 px sail -> (x>>3,y>>3) deltas -> run-length + delta -> 32-byte windows -> keccak256 -> key.
- H23: 434 px sail -> 2-byte (x,y) deltas -> XOR with fixed 32-byte mask -> keccak256 -> key.
- H22: 16-bit LA raster -> 16-bit x 2-byte (LE/BE) windows -> keccak256 -> key.
- H21: 434 px sail -> 2-byte (x,y) deltas -> 32-byte windows -> keccak256 -> key.
- H20: full LA raster -> 32-bit windows (LE/BE) -> keccak256 -> key.
- H19: row-0 curve as 147-byte stream -> uint16 LE/BE -> 32-byte windows -> keccak256 -> key.
- H18: 434 px sail -> (x>>3,y>>3) -> 32-bit deltas -> 32-byte windows -> keccak256 -> key.
- H17: 16-bit LA raster -> uint16 windows (LE/BE) -> keccak256 -> key.
- H16: 4 windows of the head/mid/tail of the full LA raster -> Python bytes -> 32-byte windows -> keccak256 -> key.
- H15: skyline top-edge (160/76/77/60) -> 2-byte windows (uint16 LE/BE) + 32-byte windows -> keccak256 -> key.
- H14: row-0 curve as 147 values -> 2-byte windows (uint16) -> keccak256 -> key.
- H13: 434 px sail outline -> 2-byte (x,y) deltas -> run-length + delta -> 32-byte windows -> keccak256 -> key.
- H12: full LA raster -> 16-bit sweep (uint16), then 32-byte windows -> keccak256 -> key.
- H11: 434 px sail outline -> (x>>3,y>>3) deltas -> XOR with fixed 32-byte mask -> keccak256 -> key.
- H10: row-0 curve as 147-byte stream -> 5-bit packed -> 32-byte window -> keccak256 -> key.
- H9: full 8-bit LA raster (gray+alpha, both byte orders) -> 32-byte windows -> keccak256 -> key.
- H8: 434 px sail -> (x>>3,y>>3) deltas -> 32 bytes -> keccak256 -> key.
- H7: row-0 curve as 147-value uint8 sequence -> XOR with fixed 32-byte mask -> keccak256 -> key.
- H6: sail outline as a closed polyline: 434 px -> 2-byte (x,y) deltas -> keccak256 -> key.
- H5: skyline top-edge as 1-byte symbols (quantized to 256 bins) + 2-byte widths -> windowed key.
- H1: skyline top-edge (160/76/77/60) -> uint16 BE/LE + height-width combos -> 0 hits.
- H2: sail alpha/outline as (x,y) 2-byte walk, endian-swapped, 5-bit symbols -> 0 hits.
- H3: row-0 curve de-interpolated to 32 bytes -> 0 hits.
- H4: building heights as discrete 2-byte BE/LE -> 0 hits.
All gated against oracle; all 0. These are HYPOTHESES, not closed facts. Next concrete probes:
- H5: skyline top-edge as 1-byte symbols (quantized to 256 bins) + 2-byte widths -> windowed key.
- H6: sail outline as a closed polyline: 434 px -> map to 32-byte key via (x>>3,y>>3) deltas -> windowed key.
- H7: row-0 curve as a 147-value uint8 sequence -> XOR with a fixed 32-byte mask, then keccak256 -> key.
