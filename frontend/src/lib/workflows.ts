import { useCallback, useEffect, useState } from 'react';
import api, { getApiErrorMessage, type MaintenanceJob } from '@/lib/api';

export const categories = ['general','plumbing','electrical','appliances','structural','security','other'];
export const pretty = (s: string) => ({move_in:'Check-in',move_out:'Check-out'}[s] || s.replaceAll('_',' '));
export const when = (s: string | null) => s ? new Date(s).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}) : 'Not yet scheduled';
export interface Repair extends Omit<MaintenanceJob,'status'> {
  status:string; category:string; description:string; requires_quotation:boolean;
  suggested_provider:{id:number;username:string}|null; visit_at:string|null; due_at:string|null;
  completion_notes:string; has_completion_photo:boolean; tenant_response:string;
  conversation_id:number|null; approved_budget:string|null;
  contact:{name:string;phone:string;email:string}; offer_expires_at:string|null;
  inspection_photos:{id:number;caption:string}[];
}
export interface Inspection {
  id:number;unit:number;unit_number:string;property_name:string;tenant:number|null;tenant_name:string;
  inspector:number|null;inspector_name:string;inspection_type:string;inspection_date:string;
  scheduled_at:string|null;requested_at:string|null;purpose:string;status:string;condition:string;
  checklist:Record<string,unknown>;notes:string;issues_found:string;recommended_actions:string;
  completed_at:string|null;acknowledged_at:string|null;agrees_with_report:boolean|null;tenant_comments:string;
  proposed_charge:string|null;charge_reason:string;charge_response:string;charge_comments:string;
  maintenance_id:number|null;photos:{id:number;caption:string}[];check_in_report:Inspection|null;
}
export function useRecords<T>(path:string) {
  const [items,setItems]=useState<T[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const load=useCallback(async()=>{setLoading(true);try {const r=await api.get<T[]>(path);setItems(r.data);setError('');} catch(e){setError(getApiErrorMessage(e,'Could not load records.'));}finally{setLoading(false);}},[path]);
  useEffect(()=>{let active=true;queueMicrotask(()=>{if(active)void load();});return()=>{active=false;};},[load]);
  return {items,loading,error,load};
}
export function formValues(form:HTMLFormElement) {return Object.fromEntries(new FormData(form).entries());}
export function uploadForm(form:HTMLFormElement) {const data=new FormData(form);for(const [key,v] of data.entries())if(v instanceof File&&!v.size)data.delete(key);return data;}
export async function postAction(path:string,action:string,data:unknown={}) {
  return api.post(`${path}/actions/${action}/`,data,data instanceof FormData?{headers:{'Content-Type':'multipart/form-data'}}:undefined);
}
