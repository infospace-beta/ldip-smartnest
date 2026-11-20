const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const exportsForPolicy={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/profile-policy.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exportsForPolicy});
const check=exportsForPolicy.shouldLoadWorkspaceProfile;
test('recovery initialization and auth changes do not fetch a workspace profile',()=>{
  for(const path of ['/auth/recovery','/reset-password','/forgot-password','/reset-password/']) {
    for(const event of ['INITIAL_SESSION','SIGNED_IN','TOKEN_REFRESHED'])assert.equal(check(path,event),false);
  }
  assert.equal(check('/login','PASSWORD_RECOVERY'),false);
});
test('ordinary sign-in and dashboard sessions keep backend authorization checks',()=>{
  for(const path of ['/login','/dashboard','/dashboard/settings'])assert.equal(check(path,'SIGNED_IN'),true);
});

test('magic-link landing never fetches an old workspace profile before verification',()=>{
  for(const path of ['/auth/magic-link','/auth/magic-link/']) {
    for(const event of ['INITIAL_SESSION','SIGNED_IN','TOKEN_REFRESHED'])assert.equal(check(path,event),false);
  }
});
