"use client";
import {useCallback, useEffect, useState} from 'react';
import {useAuth} from '@/contexts/AuthContext';
import api, {getApiErrorMessage} from '@/lib/api';

interface Attempt {id:string; amount:string; status:string;}
interface State {enabled:boolean; amount:string|null; attempts:Attempt[];}
export default function MpesaSandbox() {
  const {user}=useAuth();
  const [state,setState]=useState<State|null>(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const [requestKey,setRequestKey]=useState<string|null>(null);
  const load=useCallback(async()=>{const {data}=await api.get<State>('/payments/mpesa/');setState(data);},[]);
  const role=user?.role;
  useEffect(()=>{if(role!=='tenant')return;let active=true;void api.get<State>('/payments/mpesa/').then(({data})=>{if(active)setState(data);}).catch(e=>{if(active)setError(getApiErrorMessage(e,'Could not load M-Pesa sandbox.'));});return()=>{active=false;};},[role]);
  if(role!=='tenant')return null;
  return <section className="panel flow-card" style={{marginBottom:20}}><span className="flow-badge">Sandbox only</span><h2>M-Pesa integration test</h2><p>This tests Daraja only. It never marks your rent as paid or changes real payment records.</p>{error&&<p role="alert">{error}</p>}
    {!state?.enabled?<p>Sandbox activation is pending a Daraja app and public HTTPS callback.</p>:<form className="flow-form" onSubmit={e=>{e.preventDefault();const phone=String(new FormData(e.currentTarget).get('phone'));const key=requestKey||crypto.randomUUID();setRequestKey(key);setBusy(true);setError('');void api.post('/payments/mpesa/',{phone,idempotency_key:key}).then(load).catch(e=>setError(getApiErrorMessage(e,'Could not start the sandbox test.'))).finally(()=>setBusy(false));}}><p>Configured rent amount: KES {state.amount||'Not configured'}. The amount is calculated by the server.</p><label>Sandbox phone number<input name="phone" type="tel" required placeholder="+254712345678" autoComplete="tel"/></label><button className="button button-primary" disabled={busy||!state.amount}>Send sandbox STK prompt</button>{requestKey&&<button type="button" className="button button-secondary" disabled={busy} onClick={()=>setRequestKey(null)}>Start a different test request</button>}</form>}
    {state?.attempts.map(attempt=><div className="flow-row" key={attempt.id}><span>KES {attempt.amount} · {attempt.status.replaceAll('_',' ')}</span>{!['sandbox_success','sandbox_failed'].includes(attempt.status)&&state.enabled&&<button className="button button-secondary" disabled={busy} onClick={()=>{setBusy(true);setError('');void api.post(`/payments/mpesa/${attempt.id}/query/`).then(load).catch(e=>setError(getApiErrorMessage(e,'Could not check sandbox status.'))).finally(()=>setBusy(false));}}>Check sandbox status</button>}</div>)}
  </section>;
}
