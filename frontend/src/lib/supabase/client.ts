import { sessionCookieSecurity } from "@/lib/supabase/cookie-security";
import { createBrowserClient, parseCookieHeader, serializeCookieHeader } from "@supabase/ssr";
import { supabaseConfig } from "./config";
import { signupFetch } from "./signup-fetch";
export function createClient(){
  const {url,key}=supabaseConfig();
  return createBrowserClient(url,key,{global:{fetch:signupFetch(url)},cookies:{
    getAll:()=>typeof document==='undefined'?[]:parseCookieHeader(document.cookie).map(c=>({name:c.name,value:c.value??''})),
    setAll(values){const trusted=document.cookie.split('; ').includes('sn-trusted=1');values.forEach(({name,value,options})=>{document.cookie=serializeCookieHeader(name,value,{...options,...sessionCookieSecurity(typeof window !== 'undefined' && window.location.protocol === 'https:'),expires:undefined,maxAge:!value?0:trusted?604800:undefined});});}
  }});
}
