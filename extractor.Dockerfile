FROM python:3.13-slim
USER 0
WORKDIR /app
RUN pip install --no-cache-dir aiohttp==3.14.5 yt-dlp==2026.10.26 yt-dlp-ejs==0.8.0
RUN python -c "import urllib.request,hashlib,tarfile,io,shutil,os,platform; arch={'x86_64':'x64','aarch64':'arm64'}[platform.machine()]; sums={'x64':'cdeb8670a0c81f51b4dc4ac61919f9b1ad917b304bf8221eb939570663d240f8','arm64':'2babb9eb5264860d540849f4b064a6fbdebcdc323657d9d382ce23d313fd5e09'}; name='node-v22.23.5-linux-'+arch; b=urllib.request.urlopen('https://nodejs.org/dist/v22.23.5/'+name+'.tar.xz').read(); assert hashlib.sha256(b).hexdigest()==sums[arch]; t=tarfile.open(fileobj=io.BytesIO(b),mode='r:xz'); shutil.copyfileobj(t.extractfile(name+'/bin/node'),open('/usr/local/bin/node','wb')); os.chmod('/usr/local/bin/node',0o755)"
RUN pip install --no-cache-dir playwright==1.65.1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
RUN playwright install --with-deps --only-shell chromium && chmod -R a+rX /ms-playwright
COPY cinema /app/cinema
RUN chmod -R a+rX /app/cinema
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT ["python","-m","cinema.extractor"]
