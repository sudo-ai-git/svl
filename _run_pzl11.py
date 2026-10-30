
import sys, os
pkg = os.path.join('/home/sudosudo/.openclaw/workspace', 'venv_pkg')
if pkg not in sys.path:
    sys.path.insert(0, pkg)
# remove any prior stale venv_pkg entry
sys.path = [p for p in sys.path if p != '/home/sudosudo/.openclaw/workspace']
if pkg not in sys.path:
    sys.path.insert(0, pkg)
print("=== sys.path ===")
for p in sys.path: print(']', p)
print("=== running ===")
exec(open('/home/sudosudo/.openclaw/workspace/pzl11_solve2.py').read())
