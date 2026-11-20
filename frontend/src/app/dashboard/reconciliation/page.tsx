"use client";

import { RecordsPage } from "@/components/WorkspacePages";
import MpesaSandbox from "@/components/MpesaSandbox";

export default function PaymentsRoute() {
  return <><MpesaSandbox/><RecordsPage page="reconciliation" /></>;
}
