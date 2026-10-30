#!/usr/bin/env python3
"""Trace the sail OUTLINE path (contour) for the 434 alpha<256 sail cells.

The notes' open lead is the sail alpha-outline PATH. Row-major raster scattered
434 cells across the 552x725 bbox. A CONTIGUOUS path (following the silhouette)
may carry the byte stream differently.

This implements a clockwise contour trace: start at the top-left endpoint of
the largest alpha<256 connected component, then walk the boundary, always
turning clockwise (right-hand rule) when a walkable neighbor exists.
"""

import numpy as np
from PIL import Image

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
arr = np.array(Image.open(IMG))
g = arr[:,:,0].astype(np.uint8)
a = arr[:,:,1].astype(np.uint8)
ys, xs = np.where(a < 255)

# connected component (8-conn) to find the sail, pick the largest
from collections import deque
H, W = a.shape
seen = np.zeros_like(a, dtype=bool)
comps = []
for i in range(H):
    for j in range(W):
        if a[i,j] < 255 and not seen[i,j]:
            q = deque([(i,j)]); seen[i,j]=True; comp=[]
            while q:
                y,x = q.popleft(); comp.append((y,x))
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        ny,nx = y+dy, x+dx
                        if 0<=ny<H and 0<=nx<W and not seen[ny,nx] and a[ny,nx]<255:
                            seen[ny,nx]=True; q.append((ny,nx))
            comps.append(comp)
print("components:", len(comps), "sizes:", sorted([len(c) for c in comps], reverse=True)[:5])

# largest component
comp = max(comps, key=len)
print("largest comp size:", len(comp))

# start at top-leftest endpoint
ys_c, xs_c = zip(*comp)
start = min(comp, key=lambda p:(p[0], p[1]))
order = [start]
# 8-dir order: prefer clockwise (right-hand boundary) -> right, down-right, down, down-left, left, up-left, up, up-right
dirs = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
# we trace taking the boundary; a simple connected-path DFS with a visited set
visited = set([start])

# iterative DFS but with dir preference to make it a "path"
# simpler: just connected-path DFS in a fixed dir order, collecting order
stack = [start]
visited = set()
order = []
while stack:
    cur = stack.pop()
    if cur in visited:
        continue
    visited.add(cur)
    order.append(cur)
    # push neighbors in a deterministic clockwise-ish order so the path follows contour
    y,x = cur
    for dy,dx in dirs:
        ny,nx = y+dy, x+dx
        if 0<=ny<H and 0<=nx<W and not visited.get((ny,nx)) and a[ny,nx]<255:
            stack.append((ny,nx))

# verify count
print("traced order count:", len(order), "visited:", len(visited))

# alpha values in path order
av_path = a[order]
print("alpha in path order:", av_path.tolist()[:40])
print("alpha path order sha256(first32):", __import__('hashlib').sha256(av_path).hexdigest()[:16])
