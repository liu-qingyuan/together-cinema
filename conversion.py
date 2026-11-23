"""Durable video ingestion: queue privately, publish only completed MP4 files."""
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from subtitles import extract_subtitles, remove_subtitles

CONVERSION_EXTENSIONS = {'.mkv', '.avi'}


def write_job(data_dir, job):
    folder = Path(data_dir) / 'conversions'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (job['id'] + '.json')
    temporary = folder / (job['id'] + '.' + secrets.token_hex(4) + '.tmp')
    temporary.write_text(json.dumps(job, ensure_ascii=False))
    temporary.replace(path)


def list_jobs(data_dir):
    folder = Path(data_dir) / 'conversions'
    jobs = []
    for p in folder.glob('*.json'):
        try:
            jobs.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return sorted(jobs, key=lambda j: j['created_at'], reverse=True)


def enqueue(data_dir, source, original):
    """Take ownership of an uploaded video and return its persisted queued job."""
    data_dir = Path(data_dir)
    incoming = data_dir / 'incoming'
    incoming.mkdir(parents=True, exist_ok=True)
    ident = secrets.token_hex(8)
    job = {'id': ident, 'name': original, 'bytes': source.stat().st_size,
           'status': 'queued', 'progress': 0, 'mode': None,
           'created_at': time.time(), 'output': None, 'error': None}
    # Fixed private spool suffix preserves old jobs; ffprobe detects container bytes.
    source.replace(incoming / (ident + '.mkv'))
    write_job(data_dir, job)
    return job


def free_bytes(data_dir):
    disk = os.statvfs(data_dir)
    return disk.f_bavail * disk.f_frsize


def probe(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-max_alloc', '134217728',
         '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format',
         '-of', 'json', str(path)], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise ValueError('无法识别视频，文件可能损坏或编码不受支持')
    return json.loads(result.stdout)


def conversion_command(source, output, progress, metadata):
    videos = [s for s in metadata['streams'] if s['codec_type'] == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    audio = [s for s in metadata['streams'] if s['codec_type'] == 'audio']
    if not videos:
        raise ValueError('视频中没有可播放的视频轨道')
    v = videos[0]
    if v.get('color_transfer') in ('smpte2084', 'arib-std-b67'):
        raise ValueError('HDR 视频暂不自动转换，请先在电脑上转换为 SDR 视频')
    copy_video = (v.get('codec_name') == 'h264' and v.get('pix_fmt') == 'yuv420p'
                  and v.get('profile') in ('Constrained Baseline', 'Baseline', 'Main', 'High')
                  and v.get('width', 0) <= 1920 and v.get('height', 0) <= 1080
                  and v.get('level', 99) <= 42)
    hevc_copy = (v.get('codec_name') == 'hevc' and v.get('profile') == 'Main'
                 and v.get('pix_fmt') == 'yuv420p' and v.get('width', 0) <= 1920
                 and v.get('height', 0) <= 1080)
    copy_video = copy_video or hevc_copy
    copy_audio = (not audio or (audio[0].get('codec_name') == 'aac'
                               and audio[0].get('profile') == 'LC'
                               and audio[0].get('channels', 0) <= 2))
    mode = 'transcode' if not copy_video else ('remux' if copy_audio else 'audio')
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-max_alloc', '134217728',
               '-threads', '1', '-filter_threads', '1', '-protocol_whitelist', 'file,pipe', '-i', str(source),
               '-map', '0:' + str(v['index']), '-map_metadata', '-1', '-map_chapters', '-1', '-sn']
    if audio:
        command += ['-map', '0:' + str(audio[0]['index'])]
    if copy_video:
        command += ['-c:v', 'copy']
        if hevc_copy:
            command += ['-tag:v', 'hvc1']
    else:
        command += ['-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '23',
                    '-profile:v', 'high', '-level:v', '3.1', '-r', '30',
                    '-vf', "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p"]
    if audio:
        command += ['-c:a', 'copy'] if copy_audio else ['-c:a', 'aac', '-ac', '2', '-b:a', '128k']
    command += ['-movflags', '+faststart', '-progress', str(progress), '-nostats', '-y', str(output)]
    return command, mode


def process_job(data_dir, job, reserve):
    """Process one queued job; the final MP4 becomes visible only after success."""
    data_dir = Path(data_dir)
    media = data_dir / 'media'
    media.mkdir(exist_ok=True)
    folder = data_dir / 'conversions'
    source = data_dir / 'incoming' / (job['id'] + '.mkv')
    temporary = media / ('.' + job['id'] + '.processing.mp4')
    progress = folder / (job['id'] + '.progress')
    error_log = folder / (job['id'] + '.log')
    cancel = folder / (job['id'] + '.cancel')
    process = None
    output_name = None
    job.update(status='running', progress=0, error=None, attempts=job.get('attempts', 0) + 1)
    write_job(data_dir, job)
    try:
        if source.is_symlink() or not source.is_file():
            raise ValueError('上传的源文件不存在')
        if free_bytes(data_dir) < reserve:
            raise ValueError('可用空间不足，已保留系统磁盘余量')
        metadata = probe(source)
        stem = Path(job['name']).stem.replace('\\', '_').encode('utf-8')[:160].decode('utf-8', errors='ignore')
        output_name = job['id'] + '-' + stem + '.mp4'
        command, mode = conversion_command(source, temporary, progress, metadata)
        job.update(mode=mode, output=output_name)
        write_job(data_dir, job)
        duration = float(metadata.get('format', {}).get('duration', 0) or 0)
        with error_log.open('wb') as errors:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
            while process.poll() is None:
                if cancel.exists():
                    raise InterruptedError('已取消处理，并清理服务器上的源文件')
                if free_bytes(data_dir) < reserve:
                    raise ValueError('转换中空间不足，已停止处理以保留系统余量')
                if duration > 0 and progress.exists():
                    with progress.open('rb') as f:
                        f.seek(max(0, progress.stat().st_size - 4096))
                        values = f.read().decode(errors='replace').splitlines()
                    positions = [float(x.split('=', 1)[1]) for x in values if x.startswith('out_time_us=') and x[12:].lstrip('-').isdigit()]
                    if positions:
                        job['progress'] = max(0, min(99, int(positions[-1] / 1e6 / duration * 100)))
                        write_job(data_dir, job)
                time.sleep(.5)
        if process.returncode:
            raise ValueError('转码失败，文件可能损坏或编码不受支持；可清理任务后重新上传')
        if cancel.exists():
            raise InterruptedError('已取消处理，并清理服务器上的源文件')
        result = probe(temporary)
        video = next((s for s in result['streams'] if s['codec_type'] == 'video'), {})
        if video.get('codec_name') != 'h264' or temporary.stat().st_size == 0:
            raise ValueError('输出文件检查失败，没有加入片库')
        remove_subtitles(data_dir, output_name)
        subtitle_manifest = extract_subtitles(data_dir, source, output_name, metadata)
        if cancel.exists():
            raise InterruptedError('已取消处理，并清理服务器上的源文件')
        temporary.replace(media / output_name)
        job['subtitle_count'] = len(subtitle_manifest['tracks'])
        job['unsupported_subtitle_count'] = subtitle_manifest['unsupported_count']
        job.update(status='done', progress=100)
        write_job(data_dir, job)
        source.unlink(missing_ok=True)
    except (ValueError, OSError, subprocess.TimeoutExpired, InterruptedError) as error:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        job.update(status='cancelled' if isinstance(error, InterruptedError) else 'failed', error=str(error))
        write_job(data_dir, job)
        if isinstance(error, InterruptedError):
            source.unlink(missing_ok=True)
    finally:
        if output_name and job['status'] != 'done':
            remove_subtitles(data_dir, output_name)
        temporary.unlink(missing_ok=True)
        progress.unlink(missing_ok=True)
        cancel.unlink(missing_ok=True)
        # Failure details are the bounded user-facing message, not unbounded codec logs.
        error_log.unlink(missing_ok=True)


def work_once(data_dir, reserve):
    folder = Path(data_dir) / 'conversions'
    for job in reversed(list_jobs(data_dir)):
        cancel = folder / (job['id'] + '.cancel')
        if cancel.exists() and job['status'] in ('queued', 'failed'):
            (Path(data_dir) / 'incoming' / (job['id'] + '.mkv')).unlink(missing_ok=True)
            cancel.unlink(missing_ok=True)
            job.update(status='cancelled', error='已取消并清理服务器源文件')
            write_job(data_dir, job)
        elif job['status'] == 'queued':
            process_job(data_dir, job, reserve)
            return True
    return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', '/data'))
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    reserve = int(os.environ.get('RESERVE_BYTES', str(2 * 1024**3)))
    # A killed worker retries once, then reports a bounded resource/interruption error.
    for job in list_jobs(args.data_dir):
        if job['status'] == 'running':
            job['status'] = 'queued' if job.get('attempts', 0) < 2 else 'failed'
            job['error'] = '上次转换被中断，可能超出内存限制；请清理后重新上传' if job['status'] == 'failed' else None
            write_job(args.data_dir, job)
    while True:
        work_once(args.data_dir, reserve)
        if args.once:
            break
        time.sleep(1)
