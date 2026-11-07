const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/supabase/cookie-security.ts'), 'utf8');
function policy(mode, https) {
  const output = {};
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, {exports:output,process:{env:{NODE_ENV:mode}}});
  return output.sessionCookieSecurity(https);
}
test('production auth cookies are always Secure and SameSite Lax', () => {
  for (const https of [true,false]) {
    const options = policy('production',https);
    assert.equal(options.secure,true);assert.equal(options.sameSite,'lax');assert.equal(options.path,'/');
  }
});
test('local HTTP development remains usable while HTTPS development gets Secure cookies', () => {
  assert.equal(policy('development',false).secure,false);
  assert.equal(policy('development',true).secure,true);
});
