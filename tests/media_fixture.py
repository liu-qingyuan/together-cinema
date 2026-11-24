"""Tiny real MP4 inputs for upload contracts; no personal media or network."""
import functools
import subprocess
import tempfile
from pathlib import Path


@functools.cache
def mp4(codec="libx264"):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=12",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.5",
                        "-pix_fmt", "yuv420p", "-c:v", codec, "-c:a", "aac",
                        "-movflags", "+faststart", str(path)], check=True)
        return path.read_bytes()
