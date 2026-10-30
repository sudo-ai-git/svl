from Crypto.Hash import keccak
def kc(b):
    h=keccak.new(digest_bits=256); h.update(b); return h.digest()
Gx = bytes.fromhex('79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798')
Gy = bytes.fromhex('483ada7726a3c4655da4fbfc0e4e8cd91a91a30b8e862f3d333c082c1724a9c0')
p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
y2 = (int.from_bytes(Gy,'big')**2) % p
x3 = (int.from_bytes(Gx,'big')**3) % p
print('Gy^2 mod p:', y2)
print('Gx^3+7 mod p:', (x3+7) % p)
print('on curve:', y2 == (x3+7) % p)
uncomp = b'\x04' + Gx + Gy
print('keccak256(uncompressed):', kc(uncomp).hex())
print('addr:', kc(uncomp)[12:].hex())
