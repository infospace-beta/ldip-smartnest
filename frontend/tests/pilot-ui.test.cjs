const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const ts=require('typescript');
function load(file){const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;vm.runInNewContext(code,{exports,require:()=>({})});return exports;}
const {describeApiFailure}=load('lib/api-errors.ts');const {matchesSearch}=load('components/RecordFilters.tsx');
test('connection failures offer safe guidance for reads and uncertain writes',()=>{
  assert.match(describeApiFailure({code:'ERR_NETWORK',config:{method:'get'}},'fallback'),/could not reach SmartNest.*try again/);
  assert.match(describeApiFailure({code:'ERR_NETWORK',config:{method:'post'}},'fallback'),/whether your change was saved/);
  assert.match(describeApiFailure({code:'ETIMEDOUT',config:{method:'patch'}},'fallback'),/whether your change was saved/);
});
test('server and rate-limit failures remain errors without exposing HTML diagnostics',()=>{
  assert.match(describeApiFailure({response:{status:503,data:'<html>debug trace</html>'}},'fallback'),/temporarily unavailable/);
  assert.match(describeApiFailure({response:{status:429}},'fallback'),/Wait a moment/);
  assert.equal(describeApiFailure({response:{status:400,data:{email:['Enter a valid email.']}}},'fallback'),'email: Enter a valid email.');
});
test('permission and session errors keep useful backend details',()=>{
  assert.equal(describeApiFailure({response:{status:403,data:{detail:'Authenticator verification is required.'}}},'fallback'),'Authenticator verification is required.');
  assert.match(describeApiFailure({response:{status:401}},'fallback'),/Sign in again/);
});
test('search matches multiple words across name, home and reference fields',()=>{
  assert.equal(matchesSearch(['Amina Hassan','Acacia Court','A-03'],'  AMINA  a-03 '),true);
  assert.equal(matchesSearch(['Amina Hassan','Acacia Court','A-03'],'Amina B-04'),false);
  assert.equal(matchesSearch([null,undefined,'BANK-1108-B02'],''),true);
  assert.equal(matchesSearch(['Faith', {reference:'BANK-1108-B02'}],'faith bank-1108'),true);
});
