"""Private per-film plain-text timeline. No HTML, account data or media copies."""
from contextlib import closing
import math
import sqlite3
from pathlib import Path


class DanmakuStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'danmaku.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL, time REAL NOT NULL, text TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS by_video_time ON comments(file,time,id)')
            db.execute('CREATE TABLE IF NOT EXISTS room_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, file TEXT NOT NULL, time REAL NOT NULL, text TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS by_room_video_time ON room_comments(room,file,time,id)')

    def list(self, file, room="01"):
        with closing(sqlite3.connect(self.path, timeout=3)) as db:
            return [dict(id=i, time=t, text=text) for i, t, text in db.execute(
                ('SELECT id,time,text FROM comments WHERE file=? ORDER BY time,id LIMIT 5000' if room=='01' else 'SELECT id,time,text FROM room_comments WHERE file=? AND room=? ORDER BY time,id LIMIT 5000'), ((file,) if room=='01' else (file,room)))]

    def add(self, file, text, time, room="01"):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 120:
            raise ValueError('弹幕请输入 1～120 个字')
        if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or not 0 <= time <= 604800:
            raise ValueError('无效弹幕时间')
        text = ' '.join(text.split())
        with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
            if db.execute(('SELECT COUNT(*) FROM comments WHERE file=?' if room=='01' else 'SELECT COUNT(*) FROM room_comments WHERE file=? AND room=?'), ((file,) if room=='01' else (file,room))).fetchone()[0] >= 5000:
                raise ValueError('本片弹幕已达到 5000 条上限')
            cursor = db.execute(('INSERT INTO comments(file,time,text) VALUES(?,?,?)' if room=='01' else 'INSERT INTO room_comments(file,time,text,room) VALUES(?,?,?,?)'), ((file,float(time),text) if room=='01' else (file,float(time),text,room)))
            return dict(id=cursor.lastrowid, time=float(time), text=text)

    def remove(self, file):
        with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
            db.execute('DELETE FROM comments WHERE file=?', (file,))
            db.execute('DELETE FROM room_comments WHERE file=?',(file,))
