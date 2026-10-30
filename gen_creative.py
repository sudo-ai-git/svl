#!/usr/bin/env python3
"""Creative structured readings for PZL10, tested with the VALIDATED oracle.
Hypotheses:
  A) 5 keys x 4 chars = 20 chars (mirrors PZL3's 8x4=32 and PZL12's "58 chars")
  B) word/noun readings concatenated (Tiamat's solved-sibling grammar)
  C) A1Z26 / numeric transformations of the drawn numbers
  D) genesis-block index readings
"""
import itertools

cands = set()

def add(s):
    if s: cands.add(s)

# ---- A) 4-char-per-key blocks, concatenated to 20
K1_4 = ["1248","0124","1240","2148","Dice","DICE","dice","2142","1242","1480"]
K2_4 = ["6318","0603","2018","1806","6300","6318","6318"]
K3_4 = ["0066","6600","66","ORD6","0R66","0066","ORD6","0660"]
K4_4 = ["0-19","0019","0000","0123","19","0020","2020","0000"]
K5_4 = ["0028","2800","28","NE28","G028","0028","2800"]
for a in K1_4:
    for b in K2_4:
        for c in K3_4:
            for d in K4_4:
                for e in K5_4:
                    s = a+b+c+d+e
                    add(s); add(s[:20])

# ---- B) word readings (Capitalized proper nouns + plain digits)
K1w = ["Dice","die","dice","214","124","Double","double","HanSolo","two","one"]
K2w = ["Arweave","arweave","ICO","ico","MainSale","Mainsale","20180603","6318","630","June","2018"]
K3w = ["Order66","order66","Palpatine","Sidious","DarthSidious","66","ExecuteOrder66","Emperor"]
K4w = ["","0-19","01234567890123456789","20","0to19"]
K5w = ["Genesis28","genesis28","Genesis","28","WellSeeWhatHappens","wellseewhathappens","test","We'llseewhathappens"]
for a in K1w:
    for b in K2w:
        for c in K3w:
            for d in K4w:
                for e in K5w:
                    add(a+b+c+d+e)
                    add(a+b+c+e)
                    s = a+b+c+d+e
                    if len(s) >= 20: add(s[:20])
                    if len(s) >= 24: add(s[:24])

# ---- C) numeric transformations
# dice 1,2,4 ; 6,3,18 ; 66 ; 0-19 ; 28
nums = {
 'dice': ['124','214','142','241','412','421','148','1248','7','6','10'],
 'date': ['6318','630','063','180603','20180603','63','36','27','324','63018'],
 'order': ['66','66000000','6600000','132','12','666'],
 'range': ['0-19','0123456789','012345678910111213141516171819','20','19','190'],
 'genesis': ['28','228','280','2','8','10'],
}
for a in nums['dice']:
    for b in nums['date']:
        for c in nums['order']:
            for d in nums['range']:
                for e in nums['genesis']:
                    add(a+b+c+d+e)
                    add(a+b+c+e)
                    s=a+b+c+d+e
                    if len(s)>=20: add(s[:20])

# ---- D) genesis-block index readings: messages 1,2,4 / 6,3,18 / 66 / 28
gen_msgs = {
 1:"Karthik's Birthday",2:"order is nothing more than a characteristic of the human inability to accept chaos.",
 3:"hebikvandaagalgezegthoeveelikvanjehou. RR-MK-K-E en Roetie",4:"RG08",
 6:"Monkey Capital with Daniel Harrison is a crypto scam group.",7:"Git Good",8:"More Rigs",
 10:"Good luck!",11:"Sammen for Drammen",12:"ROCK SOLID",13:"sonatix",14:"test",18:"Dedicated to my sons",
 28:"We'll see what happens",29:"To my sons future",
}
for idx in [1,2,4,6,3,18,28,66,7,8,10,11,12,13,14,29]:
    m = gen_msgs.get(idx)
    if not m: continue
    add(m)
    add(m.replace(" ",""))
    add(m.lower().replace(" ",""))
    add("".join(w.capitalize() for w in m.split()))
    add(m[:20])
    add(m.replace(" ","")[:20])

# concatenations of genesis messages in various orders
for combo in [(1,2,4),(1,2,4,28),(6,3,18),(6,3,18,28),(28,),(1,2,4,8),(1,4,2),(4,2,1),(1,28),(28,1)]:
    parts = [gen_msgs[i] for i in combo if i in gen_msgs]
    s = "".join(parts)
    add(s); add(s.replace(" ","")); add(s.lower().replace(" ",""))
    add("".join(w.capitalize() for w in s.split()))
    if len(s)>=20: add(s[:20]); add(s.replace(" ","")[:20])

cands = sorted(c for c in cands if c)
with open('/home/sudosudo/.openclaw/workspace/fam_creative.txt','w') as f:
    f.write('\n'.join(cands))
print("generated", len(cands), "creative candidates")
