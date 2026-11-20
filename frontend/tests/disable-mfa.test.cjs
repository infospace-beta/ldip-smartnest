const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const output={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/disable-mfa.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:output});
const disable=output.disableAccountMfa;
function fixture(overrides={}) {
  const calls=[];let ids=['totp-factor','phone-factor'];
  const auth={mfa:{listFactors:async()=>({data:{all:ids.map(id=>({id,status:'verified'}))},error:null}),
    unenroll:async({factorId})=>{calls.push(factorId);ids=ids.filter(id=>id!==factorId);return {error:null};}},
    refreshSession:async()=>{calls.push('refresh');return {error:null};}};
  Object.assign(auth.mfa,overrides);
  return {auth,calls,save:async()=>{calls.push('authorized-preference');}};
}
test('turning MFA off removes every enrolled factor after backend authorization',async()=>{
  const f=fixture();await disable(f.auth,f.save);
  assert.deepEqual(f.calls,['authorized-preference','totp-factor','phone-factor','refresh']);
});
test('provider listing failure leaves preferences and factors untouched',async()=>{
  const f=fixture({listFactors:async()=>({data:null,error:Error('provider unavailable')})});
  await assert.rejects(disable(f.auth,f.save),/provider unavailable/);assert.deepEqual(f.calls,[]);
});
test('backend denial prevents factor deletion',async()=>{
  const f=fixture();await assert.rejects(disable(f.auth,async()=>{throw Error('verify authenticator');}),/verify authenticator/);assert.deepEqual(f.calls,[]);
});
test('partial removal is reported as incomplete rather than off',async()=>{
  const f=fixture({unenroll:async()=>({error:Error('provider rejected removal')})});
  await assert.rejects(disable(f.auth,f.save),/removal was not completed/);assert.deepEqual(f.calls,['authorized-preference']);
});
test('remaining verified factors prevent a false success',async()=>{
  const f=fixture({unenroll:async()=>({error:null})});
  await assert.rejects(disable(f.auth,f.save),/still enrolled/);assert.deepEqual(f.calls,['authorized-preference']);
});
test('session refresh failure gives accurate sign-in guidance after removal',async()=>{
  const f=fixture();f.auth.refreshSession=async()=>({error:Error('refresh failed')});
  await assert.rejects(disable(f.auth,f.save),/Authenticators were removed. Sign out and sign in again/);
  assert.deepEqual(f.calls,['authorized-preference','totp-factor','phone-factor']);
});
