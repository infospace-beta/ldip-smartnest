"use client";
import Link from 'next/link';
import {useAuth} from '@/contexts/AuthContext';
import Inspections from '@/components/InspectionsWorkflow';
export default function Reports(){const {user,isLoading}=useAuth();return <main className="flow-public">{isLoading?<p>Loading…</p>:user?<><Link href="/dashboard">Back to workspace</Link><Inspections/></>:<Link href="/login">Sign in to view your reports</Link>}</main>;}
