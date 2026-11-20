const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

function load(relative,dependencies={}) {
  const filename=path.resolve(__dirname,'../src',relative);
  const exports={};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,require:name=>{assert.ok(name in dependencies,`Unexpected dependency ${name}`);return dependencies[name];},Request,Response,Headers,URL,JSON},{filename});
  return exports;
}
const req=(body,origin='http://localhost:3000')=>new Request('http://localhost:3000/api/auth/recovery',{method:'POST',headers:{origin,'Content-Type':'application/json'},body:JSON.stringify(body)});
const route=verifyOtp=>load('app/api/auth/recovery/route.ts',{'@/lib/supabase/server':{createClient:async()=>({auth:{verifyOtp}})}});
const success={data:{session:{access_token:'private-test-token'},user:{email_confirmed_at:'2026-11-18T12:00:00Z'}},error:null};
const hash='a'.repeat(64);

test('recovery cannot consume a token on GET or prefetch',()=>{
  assert.equal(route(()=>{throw Error('must not verify');}).GET,undefined);
});
test('recovery blocks cross-origin requests before contacting Auth',async()=>{
  let calls=0;
  const response=await route(async()=>{calls++;return success;}).POST(req({token_hash:hash},'https://other.example.test'));
  assert.equal(response.status,403);assert.equal(calls,0);
});
test('recovery verifies a hash with a fixed email type and never returns tokens',async()=>{
  let seen;
  const response=await route(async value=>{seen=value;return success;}).POST(req({token_hash:hash,type:'email',next:'https://other.example.test'}));
  assert.equal(response.status,200);assert.equal(seen.type,'recovery');assert.equal(seen.token_hash,hash);assert.equal(seen.next,undefined);
  assert.equal(await response.text(),'{"verified":true}');
  assert.equal(response.headers.get('Referrer-Policy'),'no-referrer');assert.match(response.headers.get('Cache-Control'),/no-store/);
});
test('recovery supports entering an emailed code from a different device',async()=>{
  let seen;
  const response=await route(async value=>{seen=value;return success;}).POST(req({email:' user@example.test ',token:' 123456 '}));
  assert.equal(response.status,200);assert.equal(seen.email,'user@example.test');assert.equal(seen.token,'123456');assert.equal(seen.type,'recovery');
});
test('malformed, ambiguous and oversized recovery requests never reach Auth',async()=>{
  let calls=0;const handler=route(async()=>{calls++;return success;}).POST;
  for(const body of [null,[],{}, {token_hash:'short'},{token_hash:hash,email:'user@example.test',token:'123456'},{email:'invalid',token:'123456'},{email:'user@example.test',token:'abc'},{token_hash:'x'.repeat(5000)}]) {
    const response=await handler(req(body));assert.ok([400,413].includes(response.status));
  }
  assert.equal(calls,0);
});
test('recovery does not claim success without a verified email and session',async()=>{
  for(const data of [{session:null,user:{email_confirmed_at:'yes'}},{session:{},user:{email_confirmed_at:null}}]) {
    assert.equal((await route(async()=>({data,error:null})).POST(req({token_hash:hash}))).status,400);
  }
});
test('expired and used codes, rate limits and provider outages remain failures',async()=>{
  for(const [upstream,status] of [[403,400],[429,429],[500,503]]) {
    const response=await route(async()=>({data:{},error:{status:upstream,message:'private diagnostic'}})).POST(req({token_hash:hash}));
    assert.equal(response.status,status);assert.doesNotMatch(await response.text(),/private diagnostic/);
  }
  assert.equal((await route(async()=>{throw Error('network');}).POST(req({token_hash:hash}))).status,503);
});
