"use client";
import {useState} from 'react';
import Link from 'next/link';
import {useAuth} from '@/contexts/AuthContext';
import api, {getApiErrorMessage} from '@/lib/api';

export default function SecurityRecommendation() {
  const {user, refreshProfile} = useAuth();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  if (!user || user.security_prompt_dismissed || user.mfa_enabled) return null;
  return <aside className="security-recommendation" aria-label="Account security recommendation"><div><strong>A little extra protection for your account</strong><p>We recommend adding an authenticator and a verified backup email. You can do this now or later in Settings.</p>{error && <p role="alert">{error}</p>}</div><div className="flow-actions"><Link className="button button-primary" href="/dashboard/settings">Protect my account</Link><button className="button button-secondary" disabled={busy} onClick={async () => {setBusy(true); try {await api.post('/auth/security/', {action:'dismiss_recommendation'}); await refreshProfile();} catch (e) {setError(getApiErrorMessage(e, 'Could not save your preference.'));} finally {setBusy(false);}}}>Maybe later</button></div></aside>;
}
