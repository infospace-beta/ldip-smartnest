import {supabaseConfig} from '@/lib/supabase/config';
export async function GET(){
  try{const {url,key}=supabaseConfig();const r=await fetch(`${url}/auth/v1/settings`,{headers:{apikey:key},next:{revalidate:60},signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error();const d=await r.json();return Response.json({google:d.external?.google===true,phone:d.external?.phone===true,email:d.external?.email===true,passkeys:d.passkeys_enabled===true},{headers:{'Cache-Control':'no-store'}});}
  catch{return Response.json({error:'Sign-in methods are temporarily unavailable.'},{status:503,headers:{'Cache-Control':'no-store'}});}
}
