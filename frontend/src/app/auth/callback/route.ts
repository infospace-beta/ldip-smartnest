import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
export async function GET(request:NextRequest){
  const params=request.nextUrl.searchParams,code=params.get('code'),token_hash=params.get('token_hash'),type=params.get('type');
  if(token_hash&&type==='recovery'){const target=new URL('/auth/recovery',request.url);target.searchParams.set('token_hash',token_hash);return NextResponse.redirect(target);}
  // Provider errors arrive before a session code exists. Keep them separate
  // from expired email links, and never reflect external error text or codes.
  if(params.has('error')){
    const recovery=params.get('next')==='/reset-password'||type==='recovery';
    const destination=recovery?'/auth/recovery?error=invalid_link':params.get('error_code')==='otp_expired'?'/login?auth_error=1':'/login?auth_error=oauth';
    return NextResponse.redirect(new URL(destination,request.url));
  }
  if(token_hash&&type==='magiclink'){const target=new URL('/auth/magic-link',request.url);target.searchParams.set('token_hash',token_hash);return NextResponse.redirect(target);}
  const supabase=await createClient();
  let error:unknown=new Error('Incomplete sign-in link.');
  if(code)({error}=await supabase.auth.exchangeCodeForSession(code));
  else if(token_hash&&(type==='recovery'||type==='email'||type==='magiclink'||type==='invite'||type==='signup'))({error}=await supabase.auth.verifyOtp({token_hash,type}));
  if(!error){const destination=params.get('next')==='/reset-password'||type==='recovery'?'/reset-password':'/dashboard';return NextResponse.redirect(new URL(destination,request.url));}
  return NextResponse.redirect(new URL(params.get('next')==='/reset-password'||type==='recovery'?'/auth/recovery?error=invalid_link':'/login?auth_error=1',request.url));
}
