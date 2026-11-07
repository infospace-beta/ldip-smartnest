const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

function load(relative,dependencies={},globals={}){
  const filename=path.resolve(__dirname,'../src',relative);
  const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const exports={};
  vm.runInNewContext(compiled,{exports,require:name=>{if(!(name in dependencies))throw Error(`Unexpected dependency: ${name}`);return dependencies[name];},Request,Response,Headers,URL,AbortSignal,JSON,...globals},{filename});
  return exports;
}
const config={'@/lib/supabase/config':{supabaseConfig:()=>({url:'https://project.example.test',key:'public-test-key'})}};
function relay(fetch){return load('app/api/auth/[action]/route.ts',config,{fetch}).POST;}
const request=(body,origin='http://localhost:3000')=>new Request('http://localhost:3000/api/auth/recover',{method:'POST',headers:{origin,'Content-Type':'application/json'},body:JSON.stringify(body)});

test('recovery keeps PKCE data and forces the local reset callback',async()=>{
  let seen;
  const handler=relay(async(url,options)=>{seen={url,options};return new Response('{}',{status:200});});
  const response=await handler(request({email:'sample@example.test',code_challenge:'proof'}),{params:Promise.resolve({action:'recover'})});
  assert.equal(response.status,200);
  assert.equal(seen.url.origin,'https://project.example.test');
  assert.equal(seen.url.searchParams.get('redirect_to'),'http://localhost:3000/auth/callback?next=/reset-password');
  assert.equal(JSON.parse(seen.options.body).code_challenge,'proof');
  assert.equal(response.headers.get('Cache-Control'),'no-store');
});
test('sign-in codes cannot create uninvited accounts',async()=>{
  let body;const handler=relay(async(_,options)=>{body=JSON.parse(options.body);return new Response('{}');});
  await handler(request({email:'sample@example.test',create_user:true}),{params:Promise.resolve({action:'otp'})});
  assert.equal(body.create_user,false);
});
test('cross-origin requests never reach the provider',async()=>{
  let calls=0;const handler=relay(async()=>{calls++;return new Response('{}');});
  const r=await handler(request({},'https://other.example.test'),{params:Promise.resolve({action:'recover'})});
  assert.equal(r.status,403);assert.equal(calls,0);
});
test('unsupported relay endpoints are blocked',async()=>{
  const r=await relay(()=>{throw Error('must not call provider');})(request({}),{params:Promise.resolve({action:'admin'})});
  assert.equal(r.status,404);
});
test('SMTP failures and rate limits remain errors',async()=>{
  const r=await relay(async()=>new Response(JSON.stringify({code:'unexpected_failure',msg:'Error sending recovery email'}),{status:500,headers:{'retry-after':'60'}}))(request({}),{params:Promise.resolve({action:'recover'})});
  assert.equal(r.status,500);assert.equal(r.headers.get('retry-after'),'60');assert.equal((await r.json()).msg,'Error sending recovery email');
});
test('provider outages return a retryable error',async()=>{
  const r=await relay(async()=>{throw Error('network unavailable');})(request({}),{params:Promise.resolve({action:'recover'})});
  assert.equal(r.status,503);
});
test('SDK recovery requests use the local relay without leaking API headers',async()=>{
  let seen;
  const {signupFetch}=load('lib/supabase/signup-fetch.ts');
  const fetch=signupFetch('https://project.example.test',async(input,init)=>{seen={input,init};return new Response('{}');});
  await fetch('https://project.example.test/auth/v1/recover',{method:'POST',headers:{apikey:'provider-key'},body:JSON.stringify({email:'sample@example.test'})});
  assert.equal(seen.input,'/api/auth/recover');assert.equal(seen.init.headers.apikey,undefined);
});
function callback(auth){return load('app/auth/callback/route.ts',{
  '@/lib/supabase/server':{createClient:async()=>({auth})},
  'next/server':{NextResponse:{redirect:url=>new Response(null,{status:307,headers:{location:url.href}})}}
}).GET;}
test('recovery token hashes route to password reset',async()=>{
  let seen;
  const handler=callback({verifyOtp:async(v)=>{seen=v;return {error:null};}});
  const url=new URL('http://localhost:3000/auth/callback?token_hash=sample&type=recovery');
  const r=await handler({nextUrl:url,url:url.href});assert.equal(r.headers.get('location'),'http://localhost:3000/reset-password');assert.equal(seen.type,'recovery');
});
test('callbacks reject expired links and external destinations',async()=>{
  const url=new URL('http://localhost:3000/auth/callback?code=sample&next=https://other.example.test');
  const success=await callback({exchangeCodeForSession:async()=>({error:null})})({nextUrl:url,url:url.href});
  assert.equal(success.headers.get('location'),'http://localhost:3000/dashboard');
  const expired=await callback({exchangeCodeForSession:async()=>({error:Error('expired')})})({nextUrl:url,url:url.href});
  assert.equal(expired.headers.get('location'),'http://localhost:3000/login?auth_error=1');
});
