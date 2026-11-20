const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {AxiosHeaders}=require('axios');

function loadApi(getSession) {
  let intercept,seen;
  const instance={interceptors:{request:{use:fn=>{intercept=fn;}}},get:(url,config)=>{seen={url,config};return Promise.resolve({data:{}});}};
  const dependencies={
    axios:{default:{create:()=>instance}},
    '@/lib/supabase/client':{createClient:()=>({auth:{getSession}})},
    '@/lib/supabase/auth-errors':{authErrorMessage:error=>error.message},
    '@/lib/request-deadline':{withSessionDeadline:operation=>operation},
  };
  const exports={};
  const source=fs.readFileSync(path.join(__dirname,'../src/lib/api.ts'),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,require:name=>{assert.ok(name in dependencies,name);return dependencies[name];},process:{env:{}},window:{}});
  return {authAPI:exports.authAPI,intercept,seen:()=>seen};
}
test('profile request preserves its event token when the current session changes',async()=>{
  let lookups=0;
  const api=loadApi(async()=>{lookups++;return {data:{session:{access_token:'different-session'}},error:null};});
  await api.authAPI.me('event-session');
  const sent=api.seen();assert.equal(sent.url,'/auth/me/');
  const config={headers:new AxiosHeaders(sent.config.headers)};
  await api.intercept(config);
  assert.equal(config.headers.get('Authorization'),'Bearer event-session');assert.equal(lookups,0);
});
test('ordinary requests still attach the current Supabase session',async()=>{
  const api=loadApi(async()=>({data:{session:{access_token:'current-session'}},error:null}));
  const config={headers:new AxiosHeaders()};
  await api.intercept(config);assert.equal(config.headers.get('Authorization'),'Bearer current-session');
});
test('no session sends no bearer and a lookup error is not silently ignored',async()=>{
  const absent=loadApi(async()=>({data:{session:null},error:null}));
  const config={headers:new AxiosHeaders()};await absent.intercept(config);assert.equal(config.headers.has('Authorization'),false);
  const failed=loadApi(async()=>({data:{session:null},error:Error('session unavailable')}));
  await assert.rejects(failed.intercept({headers:new AxiosHeaders()}),/session unavailable/);
});
