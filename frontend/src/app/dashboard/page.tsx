"use client";

import { OverviewPage } from "@/components/WorkspacePages";

import { UpcomingInspection } from "@/components/InspectionsWorkflow";
import { useAuth } from "@/contexts/AuthContext";

export default function DashboardPage() {
  const {user}=useAuth();
  return <><OverviewPage />{["manager","staff","tenant"].includes(user?.role||"")&&<UpcomingInspection />}</>;
}
