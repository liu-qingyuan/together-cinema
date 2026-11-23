#!/usr/bin/env python3
"""Small source-release hygiene gate, not a comprehensive secret scanner."""
from pathlib import Path
import re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');bad=[]
for name in filter(None,paths):
 path=ROOT/name
 if name!='.env.example' and (Path(name).name.startswith('.env') or Path(name).name=='ACCESS.txt'):bad.append(name+': private config')
 if name.endswith(('.mp4','.mkv','.avi','.ts','.webm','.tar.gz','.zip')):bad.append(name+': runtime media/archive')
 try:text=path.read_text()
 except UnicodeError:continue
 # Do not match the literal generic pattern description in this checker itself.
 if path==Path(__file__).resolve():continue
 for pattern in [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'/Users/[^/\s]+/',r'C:\\Users\\']:
  if re.search(pattern,text):bad.append(name+': credential or local path pattern')
if bad:print('\n'.join(bad),file=sys.stderr);raise SystemExit(1)
print('Tracked source hygiene passed (limited patterns; manual review still required).')
