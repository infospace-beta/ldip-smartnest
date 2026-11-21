import {authRequestOrigin} from "@/lib/public-site";
import {supabaseConfig} from '@/lib/supabase/config';
export async function POST(request:Request,{params}:{params:Promise<{action:string}>}) {
  const {action}=await params;
  if(!['recover','otp','resend'].includes(action))return Response.json({msg:'Unknown authentication action.'},{status:404});
  const site=authRequestOrigin(request);
  if(request.headers.get('origin')!==site)return Response.json({msg:'Open the sign-in form on this website.'},{status:403});
  const headers={'Cache-Control':'no-store','Content-Type':'application/json'};
  if(!request.headers.get('content-type')?.includes('application/json'))return Response.json({msg:'Expected JSON.'},{status:415,headers});
  const body=await request.text();if(body.length>16384)return Response.json({msg:'Request is too large.'},{status:413,headers});
  try{const parsed=JSON.parse(body);if(action==='otp')parsed.create_user=false;if(action==='resend')parsed.type='signup';
    const {url,key}=supabaseConfig(),target=new URL(`/auth/v1/${action}`,url);
    target.searchParams.set('redirect_to',`${site}/auth/callback${action==='recover'?'?next=/reset-password':''}`);
    const upstream=await fetch(target,{method:'POST',headers:{apikey:key,Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify(parsed),cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
    const out=new Headers(headers);for(const name of ['retry-after','x-sb-error-code']){const value=upstream.headers.get(name);if(value)out.set(name,value);}
    return new Response(await upstream.text(),{status:upstream.status,headers:out});
  }catch{return Response.json({code:'auth_delivery_unavailable',msg:'The email service could not be reached. Please retry shortly or contact your administrator.'},{status:503,headers});}
}
