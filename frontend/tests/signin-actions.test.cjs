const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

function load(relative, dependencies, globals={}) {
  const exports={};
  const source=fs.readFileSync(path.join(__dirname,'../src',relative),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,require:name=>dependencies[name],URL,Response,AbortSignal,...globals});
  return exports;
}
function actions(auth) {
  return load('lib/signin-actions.ts',{'@/lib/supabase/client':{createClient:()=>({auth})},'@/lib/supabase/auth-errors':{authErrorMessage:e=>e.message}});
}
test('all social providers use the PKCE callback on this site',async()=>{
  const seen=[];
  const api=actions({signInWithOAuth:async input=>{seen.push(input);return {error:null};}});
  for(const provider of ['google','github','linkedin_oidc'])await api.startSocialSignIn(provider,'https://smartnest.example');
  assert.deepEqual(seen.map(s=>s.provider),['google','github','linkedin_oidc']);
  for(const s of seen)assert.equal(s.options.redirectTo,'https://smartnest.example/auth/callback');
});
test('magic links trim email, prevent public signup and use the same callback',async()=>{
  let sent;
  const api=actions({signInWithOtp:async input=>{sent=input;return {error:null};}});
  await api.sendMagicLink(' invited@example.test ','http://localhost:3000');
  assert.equal(sent.email,'invited@example.test');
  assert.equal(sent.options.shouldCreateUser,false);
  assert.equal(sent.options.emailRedirectTo,'http://localhost:3000/auth/callback');
});
test('provider and email failures are not reported as success',async()=>{
  const api=actions({signInWithOAuth:async()=>({error:{message:'Provider disabled'}}),signInWithOtp:async()=>({error:{message:'SMTP unavailable'}})});
  await assert.rejects(api.startSocialSignIn('github','http://localhost:3000'),/Provider disabled/);
  await assert.rejects(api.sendMagicLink('invited@example.test','http://localhost:3000'),/SMTP unavailable/);
});
test('capabilities use LinkedIn OIDC and report each provider independently',async()=>{
  const {GET}=load('app/api/auth/capabilities/route.ts',{'@/lib/supabase/config':{supabaseConfig:()=>({url:'https://auth.example',key:'public'})}},
    {fetch:async()=>new Response(JSON.stringify({external:{google:true,github:false,linkedin:true,linkedin_oidc:false,email:true}}))});
  const response=await GET(), data=await response.json();
  assert.equal(data.google,true); assert.equal(data.github,false);assert.equal(data.linkedin,false);
  assert.equal(data.email,true);assert.equal(response.headers.get('Cache-Control'),'no-store');
});
