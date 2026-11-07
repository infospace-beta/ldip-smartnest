const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {getImageProps}=require('next/image');
const filename=path.resolve(__dirname,'../src/lib/authenticator-qr.ts');
const exportsObject={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText,{exports:exportsObject,encodeURIComponent});
const {authenticatorQrSource}=exportsObject;
const svg='<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#000" width="10" height="10"/></svg>';

test('raw MFA SVG with a trailing newline is accepted by Next/Image',()=>{
  const raw=`data:image/svg+xml;utf-8,${svg}\n`;
  assert.throws(()=>getImageProps({src:raw,alt:'Test authenticator',width:200,height:200,unoptimized:true}),/cannot end with a space or control character/);
  const fixed=authenticatorQrSource(raw);
  const {props}=getImageProps({src:fixed,alt:'Test authenticator',width:200,height:200,unoptimized:true});
  assert.equal(props.src,fixed);
  assert.equal(decodeURIComponent(fixed.slice(fixed.indexOf(',')+1)),svg);
  assert.ok(fixed.includes('%23000'));
  assert.ok(!/[\r\n]/.test(fixed));
});
test('already encoded SVGs are not double encoded',()=>{
  const encoded=`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  assert.equal(authenticatorQrSource(encoded),encoded);
  assert.equal(authenticatorQrSource(authenticatorQrSource(`data:image/svg+xml;utf-8,${svg}`)),authenticatorQrSource(`data:image/svg+xml;utf-8,${svg}`));
});
test('base64 image payloads stay unchanged',()=>{
  const encoded=`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
  assert.equal(authenticatorQrSource(encoded),encoded);
});
