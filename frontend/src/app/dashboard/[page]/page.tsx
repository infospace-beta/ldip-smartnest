"use client";

import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import DashboardPage from "@/app/dashboard/page";
import AnalyticsPage from "@/app/dashboard/analytics/page";
import PropertiesPage from "@/app/dashboard/properties/page";
import TenantsPage from "@/app/dashboard/tenants/page";
import ReconciliationPage from "@/app/dashboard/reconciliation/page";
import NoticesPage from "@/app/dashboard/notices/page";
import StaffPage from "@/app/dashboard/staff/page";
import SettingsPage from "@/app/dashboard/settings/page";
import MaintenancePage from "@/app/dashboard/maintenance/page";
import ProfilePage from "@/app/dashboard/profile/page";
import HelpPage from "@/app/dashboard/help/page";
import { CommunicationsPage, TeamOnboardingPage, TenancyEventsPage } from "@/components/WorkspacePages";

const PAGE_COMPONENTS: Record<string, React.ComponentType> = {
  dashboard: DashboardPage,
  analytics: AnalyticsPage,
  properties: PropertiesPage,
  tenants: TenantsPage,
  reconciliation: ReconciliationPage,
  notices: NoticesPage,
  staff: StaffPage,
  settings: SettingsPage,
  maintenance: MaintenancePage,
  profile: ProfilePage,
  help: HelpPage,
  messages: CommunicationsPage,
  team: TeamOnboardingPage,
  "tenancy-events": TenancyEventsPage,
};

export default function DashboardRoutePage() {
  const params = useParams();
  const router = useRouter();
  const page = (params.page as string) || "dashboard";

  useEffect(() => {
    if (!PAGE_COMPONENTS[page]) {
      router.push("/dashboard/dashboard");
    }
  }, [page, router]);

  const Page = PAGE_COMPONENTS[page] || DashboardPage;
  return <Page />;
}
