const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

const site='https://smartnest-web.onrender.com';
function load(relative,dependencies={},globals={}) {
  const filename=path.join(__dirname,'../src',relative);
  const exports={};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,require:name=>{assert.ok(name in dependencies,`Unexpected dependency ${name}`);return dependencies[name];},Request,Response,Headers,URL,AbortSignal,process:{env:{NODE_ENV:'production',NEXT_PUBLIC_SITE_URL:site}},...globals});
  return exports;
}
function dependencies(auth={}) {
  return {
    '@/lib/public-site':load('lib/public-site.ts'),
    '@/lib/supabase/server':{createClient:async()=>({auth})},
    '@/lib/supabase/config':{supabaseConfig:()=>({url:'https://auth.example.test',key:'public-test-key'})},
    'next/server':{NextResponse:{redirect:url=>{
      const response=new Response(null,{status:307,headers:{location:url.href}});
      response.cookies={set(){}};
      return response;
    },next:()=>({cookies:{getAll:()=>[]}})}},
  };
}

test('successful OAuth callbacks use the public site instead of the internal bind address',async()=>{
  const {GET}=load('app/auth/callback/route.ts',dependencies({exchangeCodeForSession:async()=>({error:null})}));
  const url=new URL('http://0.0.0.0:10000/auth/callback?code=test-only&next=https://untrusted.invalid');
  const response=await GET({url:url.href,nextUrl:url});
  assert.equal(response.headers.get('location'),site+'/dashboard');
});

test('hosted recovery callbacks preserve the reset flow on the public origin',async()=>{
  const {GET}=load('app/auth/callback/route.ts',dependencies({exchangeCodeForSession:async()=>({error:null})}));
  for(const [query,destination] of [
    ['code=test-only&next=/reset-password','/reset-password'],
    ['token_hash=test-only&type=recovery','/auth/recovery?token_hash=test-only'],
    ['error=access_denied&next=/reset-password','/auth/recovery?error=invalid_link'],
  ]) {
    const url=new URL('http://0.0.0.0:10000/auth/callback?'+query);
    assert.equal((await GET({url:url.href,nextUrl:url})).headers.get('location'),site+destination);
  }
});

test('hosted recovery mail uses the public callback and rejects forged origins',async()=>{
  let calls=0,target;
  const {POST}=load('app/api/auth/[action]/route.ts',dependencies(),{fetch:async url=>{calls++;target=url;return new Response('{}');}});
  const request=origin=>new Request('http://0.0.0.0:10000/api/auth/recover',{method:'POST',headers:{origin,'content-type':'application/json','x-forwarded-host':'attacker.invalid'},body:'{"email":"pilot@example.test"}'});
  const params={params:Promise.resolve({action:'recover'})};
  assert.equal((await POST(request(site),params)).status,200);
  assert.equal(target.searchParams.get('redirect_to'),site+'/auth/callback?next=/reset-password');
  assert.equal((await POST(request('https://attacker.invalid'),params)).status,403);
  assert.equal(calls,1);
});

test('signup confirmation returns to the configured public callback',async()=>{
  let target;
  const {POST}=load('app/api/auth/signup/route.ts',dependencies(),{fetch:async url=>{target=url;return new Response('{}');}});
  const request=new Request('http://0.0.0.0:10000/api/auth/signup',{method:'POST',headers:{origin:site,'content-type':'application/json'},body:'{}'});
  assert.equal((await POST(request)).status,200);
  assert.equal(target.searchParams.get('redirect_to'),site+'/auth/callback');
});

test('hosted email verification accepts the public origin without exposing session tokens',async()=>{
  for(const action of ['confirm','magic-link','recovery']) {
    let calls=0;
    const auth={verifyOtp:async()=>{calls++;return {data:{session:{access_token:'never-return-this'},user:{email_confirmed_at:'confirmed'}},error:null};}};
    const {POST}=load(`app/api/auth/${action}/route.ts`,dependencies(auth));
    const request=new Request(`http://0.0.0.0:10000/api/auth/${action}`,{method:'POST',headers:{origin:site,'content-type':'application/json'},body:JSON.stringify({token_hash:'a'.repeat(64)})});
    const response=await POST(request);
    assert.equal(response.status,200,action);
    assert.equal(calls,1);
    assert.doesNotMatch(await response.text(),/never-return-this/);
  }
});

test('unauthenticated hosted dashboards redirect to the public login and keep the requested path',async()=>{
  const deps=dependencies();
  deps['@supabase/ssr']={createServerClient:()=>({auth:{getClaims:async()=>({data:null,error:null})}})};
  deps['@/lib/supabase/cookie-security']={sessionCookieSecurity:()=>({secure:true})};
  const {proxy}=load('proxy.ts',deps);
  const url=new URL('http://0.0.0.0:10000/dashboard/properties?search=home');
  const response=await proxy({url:url.href,nextUrl:url,cookies:{getAll:()=>[]}});
  const target=new URL(response.headers.get('location'));
  assert.equal(target.origin,site);
  assert.equal(target.pathname,'/login');
  assert.equal(target.searchParams.get('next'),'/dashboard/properties?search=home');
});

test('production authentication rejects a missing public URL while development supports localhost',()=>{
  const internal={url:'http://0.0.0.0:10000/auth/callback'};
  const production=load('lib/public-site.ts',{}, {process:{env:{NODE_ENV:'production'}}});
  assert.throws(()=>production.authRequestOrigin(internal),/NEXT_PUBLIC_SITE_URL/);
  const development=load('lib/public-site.ts',{}, {process:{env:{NODE_ENV:'development'}}});
  assert.equal(development.authRequestOrigin({url:'http://localhost:3000/auth/callback'}),'http://localhost:3000');
});
