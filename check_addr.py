from Crypto.Hash import keccak
def kc(b):
    h=keccak.new(digest_bits=256); h.update(b); return h.digest()

# The uncompressed SEC1 for generator point G (priv=1)
Gc = b'\x04' + bytes.fromhex('79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d9') + bytes.fromhex('483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0')
h = kc(Gc)
print('keccak256 of uncompressed G SEC1:', h.hex())
print('address (last 20 bytes):', h[12:].hex())
print('Famous address for priv=1:')
print('7e5f4552091a69125d5dfcb7b8c2659029395bdf')
