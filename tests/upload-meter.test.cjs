const {test}=require('node:test');
const assert=require('node:assert/strict');
require('../web/assets/upload-meter.js');
const {meter,clock,retryable}=globalThis.CinemaUpload;
const M=1048576;
test('uses useful goodput, hides cold/stale ETA, resumes with no retry double-count',()=>{
 const read=meter(64*M,0);
 assert.equal(read(0,0).seconds,null);
 assert.equal(read(M,1000).seconds,null);
 const steady=read(4*M,4000);
 assert.equal(steady.speed,1);assert.equal(steady.seconds,60);
 read(2*M,5000);const retried=read(4*M,6000);
 assert.ok(retried.speed<steady.speed);
 const stall=read(4*M,16000);assert.equal(stall.stalled,true);assert.equal(stall.seconds,null);
 assert.ok(read(6*M,18000).seconds>0);
 assert.equal(read(64*M,19000).seconds,null);
 assert.equal(clock(4760),'01:19:20');
});
test('only retries transient chunks, never resends an invalid or full-disk upload',()=>{
 for(const status of [0,408,429,500,502,503,504])assert.ok(retryable(status));
 for(const status of [400,401,403,404,409,413,507,undefined])assert.ok(!retryable(status));
});
test('accelerated chunks require trusted same-host port and a successful no-cookie probe',async()=>{
 const {lane}=globalThis.CinemaUpload, base='https://cinema.example';
 const meta={upload_port:8443,chunk_count:4}, success=async(url, options)=>{
  assert.equal(url,base+':8443/upload-healthz');assert.equal(options.credentials,'omit');
  return {status:204,headers:new Map([['X-Cinema-Upload-Ready','1']])};
 };
 assert.equal(await lane(meta,base,success),base+':8443');
 for(const m of [{...meta,upload_port:'https://elsewhere.example'},{...meta,upload_port:80},{...meta,chunk_count:1},{}]){
  assert.equal(await lane(m,base,()=>assert.fail('must not probe')),'');
 }
 assert.equal(await lane(meta,base,async()=>{throw Error('port blocked')}),'');
 assert.equal(await lane(meta,base,async()=>({status:404})),'');
});
