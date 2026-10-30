from Crypto.Hash import keccak
def kc(b):
    h=keccak.new(digest_bits=256); h.update(b); return h.digest()

# The generator point G
Gx = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
Gy = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8

# Verify G is on the curve
p = 2**256 - 2**32 - 977
print('Gy^2 mod p:', hex((Gy*Gy) % p))
print('Gx^3 + 7 mod p:', hex((Gx*Gx*Gx + 7) % p))
print('on curve:', (Gy*Gy) % p == (Gx*Gx*Gx + 7) % p)

# Uncompressed SEC1
uncomp = b'\x04' + Gx.to_bytes(32,'big') + Gy.to_bytes(32,'big')
print('uncompressed SEC1:', uncomp.hex())

# Address for priv=1
h = kc(uncomp)
print('keccak256:', h.hex())
print('address (last 20):', h[12:].hex())
print('Famous address for priv=1: 7e5f4552091a69125d5dfcb7b8c2659029395bdf')
print('Match:', h[12:].hex() == '7e5f4552091a69125d5dfcb7b8c2659029395bdf')
