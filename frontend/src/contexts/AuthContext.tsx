"use client";

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import api, { authAPI, type User, type LoginCredentials, type RegisterData } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { authErrorMessage } from "@/lib/supabase/auth-errors";
import { loadSessionProfile } from "@/lib/session-profile";
import { signupOutcome } from "@/lib/supabase/signup-outcome";
import { shouldLoadWorkspaceProfile } from "@/lib/profile-policy";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<{ requiresEmailConfirmation: boolean; mayAlreadyExist: boolean }>;
  acceptInvitation: (data: LoginCredentials & {consent:boolean; invitation_token?:string; account_invitation_token?:string}) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const invitationSignIn = useRef(false);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let generation = 0;
    ["access_token", "refresh_token", "user"].forEach((key) => localStorage.removeItem(key));
    const { data: { subscription } } = createClient().auth.onAuthStateChange((_event, session) => {
      const current = ++generation;
      if (invitationSignIn.current && session) return;
      // Run outside the SDK callback, which holds the auth lock.
      window.setTimeout(async () => {
        if (!active || current !== generation) return;
        setIsLoading(true);
        const checkProfile=shouldLoadWorkspaceProfile(window.location.pathname,_event);
        if (!session || !checkProfile) setUser(null);
        setToken(session?.access_token ?? null);
        try {
          if (session && checkProfile) {
            const { data } = await loadSessionProfile(session.access_token);
            if (active && current === generation) setUser(data);
          }
        } catch {
          if (active && current === generation) setUser(null);
        } finally {
          if (active && current === generation) setIsLoading(false);
        }
      }, 0);
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const supabase = createClient();
    const { data, error } = await supabase.auth.signInWithPassword({
      email: credentials.email.trim(),
      password: credentials.password,
    });
    if (error) throw new Error(authErrorMessage(error));
    try {
      const profile = await loadSessionProfile(data.session.access_token);
      setToken(data.session.access_token);
      setUser(profile.data);
    } catch (error) {
      await supabase.auth.signOut();
      throw error;
    }
  }, []);

  const acceptInvitation = useCallback(async (input: LoginCredentials & {consent:boolean; invitation_token?:string; account_invitation_token?:string}) => {
    invitationSignIn.current = true;
    setIsLoading(true);
    const supabase = createClient();
    let signedIn = false;
    try {
      const {data,error} = await supabase.auth.signInWithPassword({email:input.email.trim(),password:input.password});
      if (error) throw new Error(authErrorMessage(error));
      if (!data.session) throw new Error('A confirmed sign-in session is required.');
      signedIn = true;
      const profile = await api.post<User>('/auth/invitations/accept/', {
        consent:input.consent, invitation_token:input.invitation_token, account_invitation_token:input.account_invitation_token,
      });
      setToken(data.session.access_token);
      setUser(profile.data);
    } catch (error) {
      if (signedIn) {await supabase.auth.signOut({scope:'local'});setToken(null);setUser(null);}
      throw error;
    } finally {
      invitationSignIn.current = false;
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (data: RegisterData) => {
    if (!data.invitation_token && !data.account_invitation_token) throw new Error("An invitation is required. Ask your property manager or administrator.");
    if (!data.consent) throw new Error("Consent is required to create an account.");
    const { data: signup, error } = await createClient().auth.signUp({
      email: data.email.trim(), password: data.password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
        data: { username: data.username, phone: data.phone, consent: true, invitation_token: data.invitation_token, account_invitation_token: data.account_invitation_token },
      },
    });
    if (error) throw new Error(authErrorMessage(error));
    return signupOutcome(signup);
  }, []);

  const refreshProfile = useCallback(async () => {
    const response = await authAPI.me();
    setUser(response.data);
  }, []);

  const logout = useCallback(async () => {
    const { error } = await createClient().auth.signOut();
    if (error) throw error;
    setToken(null);
    setUser(null);
    router.replace("/login");
    router.refresh();
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token && !!user, isLoading, login, register, acceptInvitation, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
