"""A bounded, room-scoped screening ledger. Never stores media, URLs or viewer identities."""
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path


class WatchHistory:
    per_room = 60
    total = 4096

    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'watch-history.sqlite3'
        with closing(self._connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS screenings (id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, title TEXT NOT NULL, started INTEGER NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS screenings_room ON screenings(room,id DESC)')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=0.05)

    def list(self, room):
        with closing(self._connect()) as db:
            rows = db.execute('SELECT id,title,started FROM screenings WHERE room=? ORDER BY id DESC LIMIT ?', (room,self.per_room))
            return [dict(id=i,title=t,started=s) for i,t,s in rows]

    def record(self, room, title):
        started = int(time.time())
        with closing(self._connect()) as db, db:
            i = db.execute('INSERT INTO screenings(room,title,started) VALUES(?,?,?)',(room,title,started)).lastrowid
            db.execute('DELETE FROM screenings WHERE room=? AND id <= (SELECT id FROM screenings WHERE room=? ORDER BY id DESC LIMIT 1 OFFSET ?)', (room,room,self.per_room))
            db.execute('DELETE FROM screenings WHERE id <= (SELECT id FROM screenings ORDER BY id DESC LIMIT 1 OFFSET ?)', (self.total,))
        return dict(id=i,title=title,started=started)


def film_title(file, network):
    if file.startswith('net:'):
        source = network.sources.get(file[4:])
        title = str(source.info.get('title') or '') if source else ''
        if re.search(r'://|[?&][^ ]+=', title) or title.startswith(('/', 'www.')):
            title = ''
        return ' '.join(title.split())[:180] or '网络影片'
    name = re.sub(r'^[0-9a-f]{8,16}-','',file)
    return Path(name).stem[:180] or '本地影片'
