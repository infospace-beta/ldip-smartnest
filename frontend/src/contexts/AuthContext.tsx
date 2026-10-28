"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { authAPI, type User, type LoginCredentials, type RegisterData } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
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
    const timer = window.setTimeout(() => {
      const storedToken = localStorage.getItem("access_token");
      const storedUser = localStorage.getItem("user");
      if (!storedToken) {
        setIsLoading(false);
        return;
      }

      setToken(storedToken);
      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser) as User);
        } catch {
          localStorage.removeItem("user");
        }
      }

      authAPI.me()
        .then(({ data }) => {
          if (!active) return;
          setUser(data);
          localStorage.setItem("user", JSON.stringify(data));
        })
        .catch((error: { response?: { status?: number } }) => {
          if (!active || error.response?.status !== 401) return;
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("user");
          setToken(null);
          setUser(null);
        })
        .finally(() => {
          if (active) setIsLoading(false);
        });
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const expireSession = () => {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      setToken(null);
      setUser(null);
      router.replace("/login");
    };
    window.addEventListener("smartnest:session-expired", expireSession);
    return () => window.removeEventListener("smartnest:session-expired", expireSession);
  }, [router]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const response = await authAPI.login(credentials);
    const { user: userData, tokens } = response.data;
    localStorage.setItem("access_token", tokens.access);
    localStorage.setItem("refresh_token", tokens.refresh);
    localStorage.setItem("user", JSON.stringify(userData));
    setToken(tokens.access);
    setUser(userData);
  }, []);

  const register = useCallback(async (data: RegisterData) => {
    await authAPI.register(data);
  }, []);

  const refreshProfile = useCallback(async () => {
    const response = await authAPI.me();
    setUser(response.data);
    localStorage.setItem("user", JSON.stringify(response.data));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    setToken(null);
    setUser(null);
    router.replace("/login");
  }, [router]);

  const isAuthenticated = !!token && !!user;

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated, isLoading, login, register, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
