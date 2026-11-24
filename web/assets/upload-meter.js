/* Use useful bytes, not retransmitted traffic or the size of the preallocated file. */
(() => {
  function meter(total, now) {
    let last = now, previous = 0, rate = 0, moved = now;
    const started = now;
    return (bytes, time) => {
      const dt = (time - last) / 1000;
      if (dt > 0) {
        const useful = Math.max(bytes, previous);
        if (useful > previous) moved = time;
        const instant = (useful - previous) / dt;
        // Warm up with the observed average, then smooth over ~10 seconds.
        const weight = Math.min(1, Math.max(dt / ((time - started) / 1000), 1 - Math.exp(-dt / 10)));
        rate += (instant - rate) * weight;
        last = time; previous = useful;
      }
      const stalled = time - moved >= 12000;
      const seconds = !stalled && time - started >= 2500 && rate > 0 && bytes < total
        ? Math.ceil((total - bytes) / rate) : null;
      return {speed: stalled ? 0 : rate / 1048576, seconds, stalled};
    };
  }
  function clock(seconds) {
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
  }
  function retryable(status) {
    return status === 0 || status === 408 || status === 429 || status >= 500 && status <= 599 && status !== 507;
  }
  async function lane(meta, origin, probe = fetch) {
    const url = new URL(origin);
    if (url.protocol !== 'https:' || !Number.isInteger(meta.upload_port) ||
        meta.upload_port < 1024 || meta.upload_port > 65535 || meta.chunk_count < 2) return '';
    url.port = String(meta.upload_port);
    if (url.origin === origin) return '';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const r = await probe(url.origin + '/upload-healthz', {signal:controller.signal,
        redirect:'error', credentials:'omit', cache:'no-store'});
      return r.status === 204 && r.headers.get('X-Cinema-Upload-Ready') === '1' ? url.origin : '';
    } catch { return ''; } finally { clearTimeout(timeout); }
  }
  globalThis.CinemaUpload = {meter, clock, retryable, lane};
})();
