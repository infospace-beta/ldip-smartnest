"use client";
import {useEffect} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useAuth} from '@/contexts/AuthContext';
import AccountSecuritySettings from '@/components/AccountSecuritySettings';

export default function SecurityPage() {
  const {user, isLoading, logout} = useAuth(), router = useRouter();
  useEffect(() => {if (!isLoading && !user) router.replace('/login');}, [isLoading, user, router]);
  if (isLoading || !user) return <main className="security-card" role="status">Loading account security…</main>;
  return <main style={{maxWidth:1000, margin:'32px auto', padding:'0 20px'}}><Link className="brand" href="/dashboard">SmartNest</Link><h1>Account security</h1><AccountSecuritySettings challengeOnly={user.requires_mfa}/><div className="flow-actions" style={{marginTop:24}}>{!user.requires_mfa && <Link className="button button-secondary" href="/dashboard/settings">Back to Settings</Link>}<button className="button button-secondary" onClick={() => void logout()}>Sign out</button></div></main>;
}
