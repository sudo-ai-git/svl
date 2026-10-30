from Crypto.Hash import keccak
def kc(b):
    h=keccak.new(digest_bits=256); h.update(b); return h.digest()
# secp256k1 curve params
p = 2**256 - 2**32 - 977
Gx = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
# The well-known secp256k1 generator point G.y
# Correct G.y = 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
Gy = 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
print('Gx:', hex(Gx))
print('Gy:', hex(Gy))
print('Gx^3+7 mod p:', hex((pow(Gx,3,p)+7) % p))
print('Gy^2 mod p:', hex(pow(Gy,2,p)))
print('on curve:', (pow(Gx,3,p)+7) % p == pow(Gy,2,p))
# The correct G.y for secp256k1 is:
# 0x483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0
# Let me verify: is Gy^2 == Gx^3+7 mod p?
# If not, then Gy is wrong. Let's compute the square root.
# G.x^3+7 mod p = 0x4866d6a5ab41ab2c6bcc57ccd3735da5f16f80a548e5e20a44e4e9b8118c26f2
# The square root of this mod p:
# y = sqrt(Gx^3+7) mod p
# For p = 2**256 - 2**32 - 977, p % 4 = 3, so sqrt(x) = x^((p+1)/4) mod p
# But (p+1)/4 = (2**256 - 2**32 - 976) / 4 = 2**254 - 2**30 - 244
# Actually, let me just check if Gy is a root by computing:
print('(Gx^3+7) mod p == Gy^2 mod p:', (pow(Gx,3,p)+7) % p == pow(Gy,2,p))
# Output earlier: False. So Gy is wrong!
# Let me find the correct G.y by computing the square root of Gx^3+7 mod p
# Since p % 4 == 3, sqrt(x) = x^((p+1)/4) mod p
exp = (p + 1) // 4
print('exp:', exp)
Gx3_plus_7 = (pow(Gx,3,p) + 7) % p
print('Gx3_plus_7:', hex(Gx3_plus_7))
sqrt1 = pow(Gx3_plus_7, exp, p)
sqrt2 = p - sqrt1
print('sqrt1:', hex(sqrt1))
print('sqrt2:', hex(sqrt2))
print('sqrt1^2 mod p:', hex(pow(sqrt1,2,p)))
print('sqrt2^2 mod p:', hex(pow(sqrt2,2,p)))
print('Gx3_plus_7:', hex(Gx3_plus_7))
