"use client";
import Image from "next/image";
import { useEffect,useState,type ReactNode } from 'react';
import api from '@/lib/api';
export function WorkflowHeader({title,description,children}:{title:string;description:string;children?:ReactNode}) {
  return <header className="flow-heading"><div><div className="page-eyebrow">SmartNest operations</div><h1>{title}</h1><p>{description}</p></div>{children}</header>;
}
export function PrivatePhoto({path,label}:{path:string;label:string}) {
  const [url,setUrl]=useState(''),[error,setError]=useState('');
  useEffect(()=>{let active=true,objectUrl='';void api.get<Blob>(path,{responseType:'blob'}).then(r=>{if(active){objectUrl=URL.createObjectURL(r.data);setUrl(objectUrl);}}).catch(()=>{if(active)setError('Photo unavailable');});return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};},[path]);
  return error?<p role="alert">{error}</p>:url?<a href={url} target="_blank" rel="noreferrer"><Image unoptimized width={360} height={180} className="flow-photo" src={url} alt={label}/></a>:<p role="status">Loading photo…</p>;
}
export function ErrorBox({message}:{message:string}) {return message?<p className="auth-message" role="alert">{message}</p>:null;}
