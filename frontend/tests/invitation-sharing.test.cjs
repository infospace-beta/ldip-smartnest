const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const output={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/invitation-compose.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:output,URL,encodeURIComponent});
const link='https://smartnest.example/join-account?token=one%2Btime%26code';
test('Gmail drafts preserve the exact invitation link and selected recipient',()=>{
  const draft=new URL(output.invitationGmail(' MANAGER@EXAMPLE.TEST ','Manager & Team',link));
  assert.equal(draft.origin,'https://mail.google.com');assert.equal(draft.pathname,'/mail/');
  assert.equal(draft.searchParams.get('view'),'cm');assert.equal(draft.searchParams.get('fs'),'1');
  assert.equal(draft.searchParams.get('to'),'manager@example.test');
  assert.equal(draft.searchParams.get('su'),'Your SmartNest invitation');
  assert.ok(draft.searchParams.get('body').includes(link));
  assert.ok(draft.searchParams.get('body').startsWith('Hello Manager & Team,\n\n'));
  assert.equal(draft.searchParams.get('bcc'),null);
});
test('WhatsApp and SMS prepare drafts without sending a message',()=>{
  const whatsapp=new URL(output.invitationWhatsapp('Manager',link));
  assert.equal(whatsapp.origin,'https://wa.me');assert.ok(whatsapp.searchParams.get('text').includes(link));
  assert.ok(output.invitationSms('Manager',link).startsWith('sms:?body='));
  assert.ok(output.invitationSms('Manager',link,true).startsWith('sms:&body='));
});
test('malformed links and email header injection are rejected',()=>{
  assert.throws(()=>output.invitationGmail('person@example.test\r\nBcc:other@example.test','Person',link));
  for(const bad of ['javascript:alert(1)','https://smartnest.example/dashboard?token=test','https://user:pass@smartnest.example/join?token=test'])assert.throws(()=>output.invitationWhatsapp('Person',bad));
});
test('localhost links are distinguished from shareable site addresses',()=>{
  assert.equal(output.localOnlyInvitation('http://localhost:3000/join?token=test'),true);
  assert.equal(output.localOnlyInvitation(link),false);
});

test('all email services preserve the recipient and invitation token',()=>{
  const origins={gmail:'https://mail.google.com',outlook:'https://outlook.office.com',yahoo:'https://compose.mail.yahoo.com'};
  for(const provider of ['gmail','outlook','yahoo','default']){
    const draft=new URL(output.invitationEmailCompose(provider,' PERSON@EXAMPLE.TEST ','Person',link));
    if(provider==='default'){
      assert.equal(draft.protocol,'mailto:');
      assert.equal(decodeURIComponent(draft.pathname),'person@example.test');
    }else{
      assert.equal(draft.origin,origins[provider]);
      assert.equal(draft.searchParams.get('to'),'person@example.test');
    }
    assert.ok(draft.searchParams.get('body').includes(link));
    assert.equal(draft.searchParams.get(provider==='gmail'?'su':'subject'),'Your SmartNest invitation');
  }
});

test('direct WhatsApp drafts normalize phone numbers and fall back to recipient selection',()=>{
  const direct=new URL(output.invitationWhatsApp('+254 (712) 345-678','Person',link));
  assert.equal(direct.origin,'https://wa.me');
  assert.equal(direct.pathname,'/254712345678');
  assert.ok(direct.searchParams.get('text').includes(link));
  for(const phone of ['', '0712345678', '+254abc', '123']){
    assert.equal(new URL(output.invitationWhatsApp(phone,'Person',link)).pathname,'/');
  }
});

test('merged sharing helpers retain link and recipient validation',()=>{
  for(const provider of ['gmail','outlook','yahoo','default']){
    assert.throws(()=>output.invitationEmailCompose(provider,'person@example.test\r\nBcc:other@example.test','Person',link));
    assert.throws(()=>output.invitationEmailCompose(provider,'person@example.test','Person','javascript:alert(1)'));
  }
  assert.throws(()=>output.invitationWhatsApp('+254712345678','Person','https://smartnest.example/dashboard?token=test'));
});
