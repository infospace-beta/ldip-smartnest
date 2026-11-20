import {supabaseConfig} from '@/lib/supabase/config';
export async function GET() {
  try {
    const {url,key}=supabaseConfig();
    const response=await fetch(`${url}/auth/v1/settings`, {headers:{apikey:key}, cache:'no-store', signal:AbortSignal.timeout(8000)});
    if (!response.ok) throw Error();
    const data=await response.json();
    return Response.json({google:data.external?.google===true, github:data.external?.github===true,
      linkedin:data.external?.linkedin_oidc===true, phone:data.external?.phone===true,
      email:data.external?.email===true, passkeys:data.passkeys_enabled===true}, {headers:{'Cache-Control':'no-store'}});
  } catch {
    return Response.json({error:'Sign-in methods are temporarily unavailable.'}, {status:503, headers:{'Cache-Control':'no-store'}});
  }
}
