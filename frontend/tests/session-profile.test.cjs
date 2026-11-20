const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function loader(me) {
  const output = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/session-profile.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText,
    {exports: output, require: () => ({authAPI: {me}})});
  return output.loadSessionProfile;
}
test('concurrent sign-in and auth events share the pending profile request', async () => {
  let calls = 0, complete;
  const load = loader(() => {calls++; return new Promise(resolve => {complete = resolve;});});
  const first = load('session-a');
  assert.equal(load('session-a'), first);
  assert.equal(calls, 1);
  complete({data: {id: 1}});
  await first;
  const next = load('session-a');
  assert.notEqual(next, first);
  assert.equal(calls, 2);
  complete({data: {id: 1}});
  await next;
});
test('different sessions never share a profile and failures can be retried', async () => {
  const load = loader(() => Promise.reject(new Error('not authorized')));
  const first = load('session-a');
  const second = load('session-b');
  assert.notEqual(first, second);
  await Promise.all([assert.rejects(first, /not authorized/), assert.rejects(second, /not authorized/)]);
  const retry = load('session-a');
  assert.notEqual(retry, first);
  await assert.rejects(retry, /not authorized/);
});

test('the deduplication key is also the token passed to the API', async () => {
  const tokens=[];
  const load=loader(token=>{tokens.push(token);return Promise.resolve({data:{}});});
  const first=load('session-a');
  assert.equal(load('session-a'),first);
  const second=load('session-b');
  assert.deepEqual(tokens,['session-a','session-b']);
  await Promise.all([first,second]);
});

test('an empty token does not issue an anonymous profile request', async () => {
  let calls=0;
  const load=loader(()=>{calls++;return Promise.resolve({data:{}});});
  await assert.rejects(load('  '),/sign-in session is required/);
  assert.equal(calls,0);
});
