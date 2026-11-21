"use client";
import Link from 'next/link';
import {useCallback,useEffect,useState} from 'react';
import api,{getApiErrorMessage} from '@/lib/api';
import {useAuth} from '@/contexts/AuthContext';
import {usePathname} from 'next/navigation';

const guides:Record<string,{title:string;copy:string;href:string}[]>={
  manager:[{title:'Set up your first property',copy:'Add the building and its homes, then review availability.',href:'/dashboard/properties'},{title:'Check in and invite a tenant',copy:'Complete the move-in record before preparing the invitation.',href:'/dashboard/tenancy-events'},{title:'Invite your property team',copy:'Give staff and providers their own approved accounts.',href:'/dashboard/team'}],
  tenant:[{title:'Review your home details',copy:'Check your linked home and payment history.',href:'/dashboard/reconciliation'},{title:'Know how to report a repair',copy:'Describe the issue and coordinate access with your team.',href:'/dashboard/maintenance'},{title:'Review inspection appointments',copy:'Confirm the proposed visit or request a better time.',href:'/dashboard/unit-inspections'}],
  staff:[{title:'Explore your assigned portfolio',copy:'Review the homes and tenancies within your access.',href:'/dashboard/properties'},{title:'Review open property work',copy:'Follow repairs and coordinate the next step.',href:'/dashboard/maintenance'},{title:'Review handover records',copy:'Keep check-in and check-out details together.',href:'/dashboard/tenancy-events'}],
  maintenance:[{title:'Review your assigned jobs',copy:'Open the work order before arranging a visit.',href:'/dashboard/maintenance'},{title:'Coordinate access',copy:'Use the repair conversation to agree a visit.',href:'/dashboard/messages'},{title:'Complete your profile',copy:'Keep the contact information needed for your work current.',href:'/dashboard/profile'}],
  admin:[{title:'Review approved accounts',copy:'Manage account status and roles in Users & access.',href:'/dashboard/staff'},{title:'Review account security',copy:'Check recovery contacts and optional authenticator settings.',href:'/dashboard/settings'},{title:'Know the support process',copy:'Review help and support channels.',href:'/dashboard/help'}],
};
type Task={id:string;title:string;detail:string;href:string;kind:string;due_at:string|null};
type Inbox={counts:Record<string,number>;total:number;tasks:Task[]};

export default function WorkspaceStart(){
  const {user}=useAuth();const pathname=usePathname();
  return user&&pathname==='/dashboard'?<div className="workspace-start"><RoleGuide userId={user.id} role={user.role}/><TaskInbox key={user.id}/></div>:null;
}
export function RoleGuide({userId,role}:{userId:number;role:string}){
  const [done,setDone]=useState<number[]>([]),[hidden,setHidden]=useState(false);
  const key=`smartnest-guide-v1:${userId}:${role}`;
  useEffect(()=>{let active=true;queueMicrotask(()=>{if(!active)return;try{const saved=JSON.parse(localStorage.getItem(key)||'{}');setDone(Array.isArray(saved.done)?saved.done.filter((n:unknown)=>Number.isInteger(n)&&Number(n)>=0&&Number(n)<3):[]);setHidden(saved.hidden===true);}catch{setDone([]);setHidden(false);}});return()=>{active=false;};},[key]);
  const save=(next:number[],hide:boolean)=>{setDone(next);setHidden(hide);try{localStorage.setItem(key,JSON.stringify({done:next,hidden:hide}));}catch{/* The guide stays usable without browser storage. */}};
  const steps=guides[role]||[];
  if(hidden)return <button className="button button-secondary button-compact" type="button" onClick={()=>save(done,false)}>Show getting-started guide</button>;
  return <section className="panel flow-card" aria-labelledby="getting-started-title"><div className="flow-row"><div><h2 id="getting-started-title">Your first steps</h2><p>Follow the links, then mark each step when you are ready. {done.length} of {steps.length} complete.</p></div><button className="button button-secondary button-compact" type="button" onClick={()=>save(done,true)}>Hide guide</button></div><ol className="workspace-guide">{steps.map((step,index)=><li key={step.href}><label className="flow-check"><input type="checkbox" aria-label={`Mark ${step.title.toLowerCase()} as reviewed`} checked={done.includes(index)} onChange={()=>save(done.includes(index)?done.filter(n=>n!==index):[...done,index],false)}/><span>I have reviewed this step</span></label><h3><Link href={step.href}>{step.title}</Link></h3><p>{step.copy}</p></li>)}</ol></section>;
}
function TaskInbox(){
  const [inbox,setInbox]=useState<Inbox|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const load=useCallback(async()=>{setLoading(true);setError('');try{setInbox((await api.get<Inbox>('/dashboard/tasks/')).data);}catch(e){setInbox(null);setError(getApiErrorMessage(e,'Your next steps could not be loaded.'));}finally{setLoading(false);}},[]);
  useEffect(()=>{let active=true;queueMicrotask(()=>{if(active)void load();});return()=>{active=false;};},[load]);
  return <section className="panel flow-card" aria-labelledby="next-steps-title"><div className="flow-row"><div><h2 id="next-steps-title">Needs your attention</h2><p>Pending reviews, overdue work and inspections in the next seven days.</p></div><button type="button" disabled={loading} className="button button-secondary button-compact" onClick={()=>void load()}>{loading?'Checking…':'Refresh tasks'}</button></div>{error?<p role="alert" className="form-error">{error}</p>:loading?<p role="status">Checking your next steps…</p>:inbox?.total===0?<p>You have no pending reviews, overdue work or inspections in the next seven days.</p>:<><p role="status">{inbox?.total} items need attention{(inbox?.total||0)>(inbox?.tasks.length||0)?`; showing the first ${inbox?.tasks.length}`:''}.</p><ul className="workspace-task-list">{inbox?.tasks.map(task=><li key={task.id}><div><Link href={task.href}><strong>{task.title}</strong></Link><p>{task.detail}</p>{task.due_at&&<time dateTime={task.due_at}>{new Date(task.due_at).toLocaleString('en-KE')}</time>}</div><Link className="button button-secondary button-compact" href={task.href}>Review</Link></li>)}</ul></>}</section>;
}
