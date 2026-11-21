type Failure={code?:string;message?:string;config?:{method?:string};response?:{status?:number;data?:unknown}};
export function describeApiFailure(error:Failure,fallback:string):string{
  const read=['get','head','options'].includes(error.config?.method?.toLowerCase()||'');
  const uncertain=read?'Check your connection and try again.':'Check whether your change was saved before submitting it again.';
  if(error.code==='ECONNABORTED'||error.code==='ETIMEDOUT')return `The request took too long. ${uncertain}`;
  if(!error.response&&(error.code==='ERR_NETWORK'||error.message==='Network Error'))return `We could not reach SmartNest. ${uncertain}`;
  if(error.response?.status===429)return 'Too many requests. Wait a moment before trying again.';
  if((error.response?.status||0)>=500)return `SmartNest is temporarily unavailable. ${uncertain}`;
  const data=error.response?.data;
  if(typeof data==='string'&&data.trim()&&!data.trim().startsWith('<'))return data;
  if(data&&typeof data==='object'){
    const details=Object.entries(data).flatMap(([field,value])=>(Array.isArray(value)?value:[value]).filter((item):item is string=>typeof item==='string').map(item=>field==='detail'||field==='error'?item:`${field}: ${item}`));
    if(details.length)return details.join(' ');
  }
  if(error.response?.status===401)return 'Your session could not be verified. Sign in again to continue.';
  if(error.response?.status===403)return 'Your account does not have access to this action. Contact your property manager if you need help.';
  return fallback;
}
