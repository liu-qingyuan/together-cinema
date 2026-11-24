FROM python:3.13-slim
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /data/media /data/subtitles /data/conversions /data/incoming && chown -R 10001:10001 /data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cinema ./cinema
COPY web/index.html ./web/
COPY web/assets ./web/assets
RUN chmod -R a+rX /app/cinema /app/web
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "cinema.server"]
