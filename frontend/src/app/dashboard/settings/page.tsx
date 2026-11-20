"use client";
import {SettingsPage} from '@/components/WorkspacePages';
import AccountSecuritySettings from '@/components/AccountSecuritySettings';
import {useAuth} from '@/contexts/AuthContext';

export default function SettingsRoute() {
  const {user} = useAuth();
  return <>{user?.role === 'admin' ? <SettingsPage/> : <div className="page-header"><h1>Settings</h1><p>Manage your account and sign-in preferences.</p></div>}<h2 style={{margin:'24px 0 16px'}}>Account security</h2><AccountSecuritySettings/></>;
}
