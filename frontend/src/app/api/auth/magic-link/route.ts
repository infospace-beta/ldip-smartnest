import {authRequestOrigin} from "@/lib/public-site";
import {createClient} from '@/lib/supabase/server';

const headers = {'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'};
const reply = (body: object, status = 200) => Response.json(body, {status, headers});

// GET/prefetch must never consume an email token. Only an explicit same-site POST
// verifies it. Supabase still enforces token ownership, expiry and one-time use.
export async function POST(request: Request) {
  if (request.headers.get('origin') !== authRequestOrigin(request)) return reply({message:'Open the sign-in page on this website.'},403);
  if (!request.headers.get('content-type')?.includes('application/json')) return reply({message:'Expected JSON.'},415);
  let input;
  try {
    if (Number(request.headers.get('content-length')) > 4096) return reply({message:'Request is too large.'},413);
    const body = await request.text();
    if (body.length > 4096) return reply({message:'Request is too large.'},413);
    input = JSON.parse(body);
  } catch { return reply({message:'Invalid sign-in request.'},400); }
  if (!input || typeof input !== 'object' || Array.isArray(input)) return reply({message:'Invalid sign-in request.'},400);
  const hash = typeof input.token_hash === 'string' ? input.token_hash : '';
  const email = typeof input.email === 'string' ? input.email.trim() : '';
  const token = typeof input.token === 'string' ? input.token.trim() : '';
  const byHash = /^[a-zA-Z0-9_-]{20,1024}$/.test(hash);
  const byCode = email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && /^\d{6,10}$/.test(token);
  if ((byHash && (email || token)) || (!byHash && !byCode) || (hash && !byHash)) return reply({message:'Use the complete sign-in link, or enter the email and code from your latest email.'},400);
  try {
    const supabase = await createClient();
    // Caller-supplied OTP types and redirect destinations are intentionally ignored.
    const {data,error} = await supabase.auth.verifyOtp(byHash ? {token_hash:hash,type:'email'} : {email,token,type:'email'});
    if (error) {
      if (error.status === 429) return reply({message:'Too many attempts. Wait before trying again.'},429);
      if (error.status && error.status >= 500) return reply({message:'The sign-in service is temporarily unavailable. Try again shortly.'},503);
      return reply({message:'This sign-in link or code is invalid, expired, or already used. Request a new magic link from the sign-in page and use only its newest link or code.'},400);
    }
    if (!data.session || !data.user?.email_confirmed_at) return reply({message:'Sign-in could not be completed. Please request a new magic link.'},400);
    // The server client writes session cookies. Never return tokens in JSON.
    return reply({verified:true});
  } catch { return reply({message:'The sign-in service could not be reached. Try again shortly.'},503); }
}
