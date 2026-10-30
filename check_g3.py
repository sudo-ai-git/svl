from Crypto.Hash import keccak
def kc(b):
    h=keccak.new(digest_bits=256); h.update(b); return h.digest()
# secp256k1
p = 2**256 - 2**32 - 977
Gx = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
Gy = 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
print('Gx:', hex(Gx))
print('Gy:', hex(Gy))
print('Gx^3 mod p:', hex(pow(Gx,3,p)))
print('Gx^3+7 mod p:', hex((pow(Gx,3,p)+7) % p))
print('Gy^2 mod p:', hex(pow(Gy,2,p)))
print('on curve:', (pow(Gx,3,p)+7) % p == pow(Gy,2,p))
# Correct G.y for secp256k1
import math
# correct G.y for x = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
# on secp256k1, G.y = 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
# Let's verify this is correct by computing the square root of x^3+7 mod p
# Using Tonelli-Shanks or just checking the standard value
# The correct G.y for secp256k1 == 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
# Wait, let's check if this is the correct y by finding the other root
Gx3_plus_7 = (pow(Gx,3,p) + 7) % p
print('Gx^3+7 mod p:', hex(Gx3_plus_7))
# The two roots of y^2 = Gx3_plus_7 mod p are y and p-y
# Check if Gy is a root
print('Gy^2 mod p:', hex(pow(Gy,2,p)))
print('is Gy a root:', pow(Gy,2,p) == Gx3_plus_7)
