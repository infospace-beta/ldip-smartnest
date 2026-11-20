export function publicSiteOrigin():string|null {
  const value=process.env.NEXT_PUBLIC_SITE_URL;
  if(!value)return null;
  try {
    const url=new URL(value);
    if(url.protocol!=='https:'||url.username||url.password||url.hostname==='localhost'||url.hostname.endsWith('.invalid')||url.hostname.endsWith('.example'))return null;
    return url.origin;
  } catch {return null;}
}
export function publicIndexingEnabled() {return process.env.SMARTNEST_PUBLIC_INDEXING==='true'&&publicSiteOrigin()!==null;}
