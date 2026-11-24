#!/usr/bin/env python3
"""Small source-release hygiene gate, not a comprehensive secret scanner."""
from pathlib import Path
import hashlib,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');bad=[]
OPENING_PATH = 'web/assets/room-art/anime-opening-v1.mp4'
OPENING_SHA256 = '8e9b3fa2ce8b9e22632ec77019a7400c6a4d27aa96d8f563d5c68c45fbd6942e'
for name in filter(None,paths):
 path=ROOT/name
 if name!='.env.example' and (Path(name).name.startswith('.env') or Path(name).name=='ACCESS.txt'):bad.append(name+': private config')
 if name.endswith(('.mp4','.mkv','.avi','.ts','.webm','.tar.gz','.zip')):
  if name != OPENING_PATH or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != OPENING_SHA256:
   bad.append(name+': runtime media/archive')
  continue
 try:text=path.read_text()
 except UnicodeError:continue
 # Do not match the literal generic pattern description in this checker itself.
 if path==Path(__file__).resolve():continue
 for pattern in [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'/Users/[^/\s]+/',r'C:\\Users\\']:
  if re.search(pattern,text):bad.append(name+': credential or local path pattern')
if bad:print('\n'.join(bad),file=sys.stderr);raise SystemExit(1)
print('Tracked source hygiene passed (limited patterns; manual review still required).')
