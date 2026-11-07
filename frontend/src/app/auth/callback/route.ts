import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
export async function GET(request:NextRequest){
  const params=request.nextUrl.searchParams,code=params.get('code'),token_hash=params.get('token_hash'),type=params.get('type');
  const supabase=await createClient();
  let error:unknown=new Error('Incomplete sign-in link.');
  if(code)({error}=await supabase.auth.exchangeCodeForSession(code));
  else if(token_hash&&(type==='recovery'||type==='email'||type==='magiclink'||type==='invite'||type==='signup'))({error}=await supabase.auth.verifyOtp({token_hash,type}));
  if(!error){const destination=params.get('next')==='/reset-password'||type==='recovery'?'/reset-password':'/dashboard';return NextResponse.redirect(new URL(destination,request.url));}
  return NextResponse.redirect(new URL('/login?auth_error=1',request.url));
}
