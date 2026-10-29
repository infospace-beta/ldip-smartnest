"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { authAPI, type User, type LoginCredentials, type RegisterData } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let generation = 0;
    ["access_token", "refresh_token", "user"].forEach((key) => localStorage.removeItem(key));
    const { data: { subscription } } = createClient().auth.onAuthStateChange((_event, session) => {
      const current = ++generation;
      // Run outside the SDK callback, which holds the auth lock.
      window.setTimeout(async () => {
        if (!active || current !== generation) return;
        setUser(null);
        setToken(session?.access_token ?? null);
        try {
          if (session) {
            const { data } = await authAPI.me();
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
    const { data, error } = await supabase.auth.signInWithPassword(credentials);
    if (error) throw error;
    try {
      const profile = await authAPI.me();
      setToken(data.session.access_token);
      setUser(profile.data);
    } catch (error) {
      await supabase.auth.signOut();
      throw error;
    }
  }, []);

  const register = useCallback(async (data: RegisterData) => {
    if (!data.consent) throw new Error("Consent is required to create an account.");
    const { error } = await createClient().auth.signUp({
      email: data.email, password: data.password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
        data: { username: data.username, phone: data.phone, consent: true, invitation_token: data.invitation_token },
      },
    });
    if (error) throw error;
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
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token && !!user, isLoading, login, register, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
