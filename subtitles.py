"""Private, selectable original PGS and WebVTT tracks paired with a video."""
import json
import re
import secrets
import shutil
import subprocess
from pathlib import Path

TEXT_CODECS = {'subrip', 'ass', 'ssa', 'webvtt', 'mov_text', 'text'}


def _folder(data_dir, video_name):
    if (not video_name or Path(video_name).name != video_name or
            '\\' in video_name or video_name.startswith('.')):
        raise ValueError('无效影片名称')
    root = Path(data_dir) / 'subtitles'
    folder = root / video_name
    if root.is_symlink() or folder.is_symlink():
        raise ValueError('无效字幕目录')
    return folder


def list_subtitles(data_dir, video_name):
    folder = _folder(data_dir, video_name)
    manifest = folder / 'tracks.json'
    if not manifest.exists():
        return {'tracks': [], 'unsupported_count': 0}
    if manifest.is_symlink() or manifest.stat().st_size > 1024**2:
        raise ValueError('无效字幕清单')
    data = json.loads(manifest.read_text())
    tracks = []
    for row in data.get('tracks', []):
        ident = str(row.get('id', ''))
        fmt = row.get('format', 'vtt')
        if fmt not in ('vtt', 'pgs'):
            raise ValueError('无效字幕格式')
        path = folder / (ident + ('.sup' if fmt == 'pgs' else '.vtt'))
        if not re.fullmatch(r'[0-9]+', ident):
            raise ValueError('无效字幕轨道')
        if path.is_file() and not path.is_symlink():
            tracks.append({'id': ident, 'label': str(row.get('label', '字幕')),
                           'lang': str(row.get('lang', 'und')),
                           'default': bool(row.get('default', False)), 'format': fmt})
    return {'tracks': tracks, 'unsupported_count': int(data.get('unsupported_count', 0))}


def subtitle_path(data_dir, video_name, track_id):
    track = next((t for t in list_subtitles(data_dir, video_name)['tracks'] if t['id'] == track_id), None)
    if track is None:
        return None
    return _folder(data_dir, video_name) / (track_id + ('.sup' if track['format'] == 'pgs' else '.vtt'))


def remove_subtitles(data_dir, video_name):
    folder = _folder(data_dir, video_name)
    if folder.exists():
        shutil.rmtree(folder)


def extract_subtitles(data_dir, source, video_name, metadata):
    """Preserve PGS images as SUP and convert text tracks to WebVTT; no OCR/burn-in."""
    streams = [s for s in metadata.get('streams', []) if s.get('codec_type') == 'subtitle']
    supported = [s for s in streams if s.get('codec_name') in TEXT_CODECS | {'hdmv_pgs_subtitle'}]
    tracks = []
    for stream in supported:
        tags = stream.get('tags', {})
        lang = tags.get('language', 'und').lower()
        lang = {'chi': 'zh', 'zho': 'zh', 'eng': 'en'}.get(lang, lang)
        if not re.fullmatch(r'[a-z]{2,3}', lang):
            lang = 'und'
        tracks.append({'id': str(stream['index']),
                       'label': tags.get('title') or {'zh': '中文字幕', 'en': 'English'}.get(lang, lang),
                       'lang': lang,
                       'default': bool(stream.get('disposition', {}).get('default')),
                       'format': 'pgs' if stream.get('codec_name') == 'hdmv_pgs_subtitle' else 'vtt'})
    if tracks and not any(t['default'] for t in tracks):
        next((t for t in tracks if t['lang'] == 'zh'), tracks[0])['default'] = True
    manifest = {'tracks': tracks, 'unsupported_count': len(streams) - len(supported)}
    folder = _folder(data_dir, video_name)
    folder.parent.mkdir(parents=True, exist_ok=True)
    if folder.exists():
        raise ValueError('字幕目录已经存在')
    temporary = folder.parent / ('.extract-' + secrets.token_hex(8))
    temporary.mkdir(mode=0o700)
    try:
        if tracks:
            command = ['ffmpeg', '-v', 'error', '-nostdin', '-max_alloc', '134217728',
                       '-protocol_whitelist', 'file,pipe', '-i', str(source)]
            for track in tracks:
                codec, fmt, ext = ('copy', 'sup', '.sup') if track['format'] == 'pgs' else ('webvtt', 'webvtt', '.vtt')
                command += ['-map', '0:' + track['id'], '-c:s', codec, '-f', fmt,
                            str(temporary / (track['id'] + ext))]
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise ValueError('字幕提取失败，影片未加入片库')
            for track in tracks:
                ext, magic = ('.sup', b'PG') if track['format'] == 'pgs' else ('.vtt', b'WEBVTT')
                with (temporary / (track['id'] + ext)).open('rb') as f:
                    valid = f.read(len(magic)) == magic
                if not valid:
                    raise ValueError('字幕输出格式错误，影片未加入片库')
        (temporary / 'tracks.json').write_text(json.dumps(manifest, ensure_ascii=False))
        temporary.replace(folder)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
