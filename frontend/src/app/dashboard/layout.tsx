"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense } from "react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "@/contexts/AuthContext";
import Icon from "@/components/Icon";
import UserAvatar from "@/components/UserAvatar";

type NavItem = { label: string; href: string; icon: string; roles: string[]; section: string };

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: "dashboard", roles: ["admin", "manager", "tenant", "staff", "maintenance"], section: "Workspace" },
  { label: "Analytics", href: "/dashboard/analytics", icon: "analytics", roles: ["manager"], section: "Workspace" },
  { label: "Properties & units", href: "/dashboard/properties", icon: "properties", roles: ["manager", "staff"], section: "Portfolio" },
  { label: "Tenants & leases", href: "/dashboard/tenants", icon: "tenants", roles: ["manager", "staff"], section: "Portfolio" },
  { label: "Payments", href: "/dashboard/reconciliation", icon: "payments", roles: ["manager", "tenant"], section: "Portfolio" },
  { label: "Expenses", href: "/dashboard/expenses", icon: "expenses", roles: ["manager"], section: "Portfolio" },
  { label: "Maintenance", href: "/dashboard/maintenance", icon: "maintenance", roles: ["manager", "staff", "maintenance", "tenant"], section: "Operations" },
  { label: "Check-in & check-out", href: "/dashboard/tenancy-events", icon: "calendar", roles: ["manager", "staff"], section: "Operations" },
  { label: "Team onboarding", href: "/dashboard/team", icon: "staff", roles: ["manager"], section: "Operations" },
  { label: "Inspections", href: "/dashboard/unit-inspections", icon: "inspections", roles: ["manager", "staff"], section: "Operations" },
  { label: "Notices", href: "/dashboard/notices", icon: "notices", roles: ["admin", "manager", "staff", "tenant", "maintenance"], section: "Operations" },
  { label: "Communications", href: "/dashboard/messages", icon: "notices", roles: ["admin", "manager", "staff", "tenant", "maintenance"], section: "Communications" },
  { label: "Users & access", href: "/dashboard/staff", icon: "staff", roles: ["admin"], section: "Administration" },
  { label: "Settings", href: "/dashboard/settings", icon: "settings", roles: ["admin"], section: "Administration" },
  { label: "Help & support", href: "/dashboard/help", icon: "help", roles: ["admin", "manager", "tenant", "staff", "maintenance"], section: "Account" },
  { label: "My profile", href: "/dashboard/profile", icon: "profile", roles: ["admin", "manager", "tenant", "staff", "maintenance"], section: "Account" },
];

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    admin: "System administrator",
    manager: "Manager (Landlord)",
    staff: "Agency staff",
    tenant: "Tenant",
    maintenance: "Maintenance",
  };
  return labels[role] ?? role.replaceAll("_", " ");
}

function DashboardShell({ children }: { children: ReactNode }) {
  const { user, logout, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const role = user?.role ?? "";
  const visibleItems = useMemo(() => NAV_ITEMS.filter((item) => item.roles.includes(role)), [role]);
  const currentItem = NAV_ITEMS.find((item) => item.href === pathname);
  const activeItem = currentItem && currentItem.roles.includes(role) ? currentItem : visibleItems[0];
  const displayName = user?.username || user?.email || "SmartNest user";
  const avatarName = user?.username || user?.email || "S";

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isLoading && isAuthenticated && currentItem && !currentItem.roles.includes(role)) router.replace("/dashboard");
  }, [currentItem, isAuthenticated, isLoading, role, router]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const saved = localStorage.getItem("smartnest-theme");
      const nextTheme = saved === "dark" ? "dark" : "light";
      setTheme(nextTheme);
      document.body.classList.toggle("dark-theme", nextTheme === "dark");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("smartnest-theme", nextTheme);
    document.body.classList.toggle("dark-theme", nextTheme === "dark");
  };

  const renderNav = (items: NavItem[]) => items.map((item) => (
    <Link
      href={item.href}
      key={item.href}
      className={`nav-link ${pathname === item.href ? "active" : ""}`}
      aria-current={pathname === item.href ? "page" : undefined}
      onClick={() => setSidebarOpen(false)}
    >
      <Icon name={item.icon} />
      <span className="nav-label">{item.label}</span>
    </Link>
  ));

  if (isLoading || !isAuthenticated || (currentItem && !currentItem.roles.includes(role))) {
    return <div className="loading-state" role="status">Preparing your workspace…</div>;
  }

  const sections = [...new Set(visibleItems.map((item) => item.section))];
  return (
    <div className="app">
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? "show" : ""}`} aria-label="Main navigation">
        <Link className="brand" href="/dashboard">
          <span className="brand-mark">S</span>
          <span><span className="brand-name">SmartNest</span><span className="brand-caption">Property operations</span></span>
        </Link>
        <nav className="nav-list">
          {sections.map((section) => (
            <div key={section}>
              <div className="nav-caption">{section}</div>
              {renderNav(visibleItems.filter((item) => item.section === section))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
        </div>
      </aside>

      <div className="shell">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button>
          <div className="topbar-context">
            <div className="topbar-kicker">SmartNest workspace</div>
            <div className="topbar-title">{activeItem?.label ?? "Overview"}</div>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={toggleTheme}><Icon name={theme === "dark" ? "sun" : "theme"} /></button>
            <Link className="button button-secondary button-compact password-shortcut" href="/dashboard/profile#password">Change password</Link>
            <div className="topbar-profile">
              <UserAvatar userId={user?.id} hasAvatar={user?.has_avatar} name={avatarName} className="user-avatar" />
              <span className="topbar-profile-copy"><span className="user-name">{displayName}</span><span className="user-role">{roleLabel(role)}</span></span>
            </div>
            <button className="icon-button" aria-label="Sign out" onClick={logout}><Icon name="logout" /></button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">{renderNav(visibleItems.slice(0, 5))}</nav>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="loading-state" role="status">Preparing your workspace…</div>}>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}
