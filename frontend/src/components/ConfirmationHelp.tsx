"use client";
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {createClient} from '@/lib/supabase/client';
import {authErrorMessage} from '@/lib/supabase/auth-errors';

export default function ConfirmationHelp({email,onExisting}:{email:string;onExisting:()=>void}) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[cooldown,setCooldown]=useState(0);
  useEffect(()=>{if(!cooldown)return;const timer=setTimeout(()=>setCooldown(value=>Math.max(0,value-1)),1000);return()=>clearTimeout(timer);},[cooldown]);
  const resend=async()=>{
    setBusy(true);setMessage('');setError('');
    try{
      const {error}=await createClient().auth.resend({type:'signup',email,options:{emailRedirectTo:`${location.origin}/auth/callback`}});
      if(error){if(error.status===429)setCooldown(60);throw error;}
      setCooldown(60);setMessage(`A confirmation request was accepted for ${email}. This does not prove inbox delivery. If you already verified this email, sign in to accept instead.`);
    }catch(e){setError(e instanceof Error?authErrorMessage(e):'The confirmation email could not be requested.');}
    finally{setBusy(false);}
  };
  return <div className="hint-card" style={{margin:'14px 0'}}>
    <p>A new sign-in needs email confirmation after signup. Check the invited inbox ({email}), Spam/Junk and All Mail. Use the newest email only.</p>
    <p>Already verified this email before? Creating an account again does not change its password or send a fresh confirmation. Use your existing password to accept this invitation.</p>
    <div className="flow-actions"><button className="button button-secondary" type="button" disabled={busy||cooldown>0} onClick={()=>void resend()}>{busy?'Requesting...':cooldown?`Wait ${cooldown}s before resending`:'Resend confirmation email'}</button><button className="button button-primary" type="button" onClick={onExisting}>Sign in to accept invitation</button></div>
    <p>If the email link opens in another browser, use <Link href="/auth/confirm">email and confirmation code</Link>. If SmartNest runs at localhost, open it on the hosting PC; localhost on a phone points to the phone itself.</p>
    {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  </div>;
}
