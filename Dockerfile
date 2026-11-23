FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py conversion.py subtitles.py danmaku.py external_media.py parallel_upload.py index.html ./
COPY assets ./assets
USER 10001:10001
EXPOSE 8080
CMD ["python", "server.py"]
