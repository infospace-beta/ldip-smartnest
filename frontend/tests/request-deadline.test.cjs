const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const output = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/request-deadline.ts'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText, {exports: output, setTimeout, clearTimeout, Error});

test('stalled session lookup cannot keep an API request waiting indefinitely', async () => {
  await assert.rejects(output.withSessionDeadline(new Promise(() => {}), 10), /session could not be checked in time/);
});
test('normal sessions and auth errors retain their original result', async () => {
  const session = {access_token: 'test-token'};
  assert.equal(await output.withSessionDeadline(Promise.resolve(session), 100), session);
  const failure = new Error('session unavailable');
  await assert.rejects(output.withSessionDeadline(Promise.reject(failure), 100), (error) => error === failure);
});
