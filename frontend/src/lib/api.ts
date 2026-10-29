import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : fallback;
  }

  const data: unknown = error.response?.data;
  if (typeof data === "string" && data.trim()) return data;
  if (typeof data === "object" && data !== null) {
    const details = Object.entries(data).flatMap(([field, value]) => {
      const messages = Array.isArray(value) ? value : [value];
      return messages
        .filter((message): message is string => typeof message === "string")
        .map((message) => field === "detail" || field === "error" ? message : `${field}: ${message}`);
    });
    if (details.length) return details.join(" ");
  }
  return error.message || fallback;
}

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, { refresh: refreshToken });
          localStorage.setItem("access_token", data.access);
          localStorage.setItem("refresh_token", data.refresh);
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${data.access}`;
          }
          return api(originalRequest);
        } catch (refreshError) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("user");
          if (typeof window !== "undefined") {
            window.dispatchEvent(new Event("smartnest:session-expired"));
          }
          return Promise.reject(refreshError);
        }
      } else if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("user");
        window.dispatchEvent(new Event("smartnest:session-expired"));
      }
    }
    return Promise.reject(error);
  }
);

export default api;

export interface User {
  id: number;
  email: string;
  username: string;
  role: string;
  phone: string;
  avatar: string;
  has_avatar: boolean;
  property_cluster: string;
  is_active_user: boolean;
  portal_access_granted: boolean;
  date_joined: string;
  registration_consent_at: string | null;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  role: string;
  phone: string;
  consent: boolean;
  invitation_token?: string;
}

export interface AuthResponse {
  user: User;
  tokens: {
    refresh: string;
    access: string;
  };
}

export interface RegisterResponse {
  user: User;
  message: string;
}

export interface UserAccess {
  id: number;
  username: string;
  email: string;
  role: string;
  property_cluster: string;
  is_active_user: boolean;
  portal_access_granted: boolean;
  assigned_units: number[];
  managed_property_ids: number[];
}

export interface UserAssignmentOptions {
  properties: { id: number; name: string; owner_id: number | null }[];
  units: { id: number; unit_number: string; property_id: number; property_name: string }[];
}

export interface OnboardTeamMember {
  username: string;
  email: string;
  password: string;
  phone: string;
  role: "staff" | "maintenance";
}

export interface PublicUser {
  id: number;
  username: string;
  role: string;
  phone: string;
  property_cluster: string;
  has_avatar: boolean;
}

export interface TenantInvitationDetails {
  email: string;
  tenant_name: string;
  phone: string;
  expires_at: string;
}

export interface TenantInvitation {
  token: string;
  email: string;
  expires_at: string;
}

export interface CommunicationContact {
  id: number;
  username: string;
  role: string;
  has_avatar: boolean;
}

export interface Conversation {
  id: number;
  subject: string;
  participants: CommunicationContact[];
  created_at: string;
  last_message_preview: string;
}

export interface Message {
  id: number;
  sender: number;
  sender_name: string;
  body: string;
  sent_at: string;
}

export interface TenancyEvent {
  id: number;
  tenant: number;
  tenant_name: string;
  tenant_user_id: number | null;
  tenant_has_avatar: boolean;
  unit: number;
  unit_number: string;
  property_name: string;
  action: "check_in" | "check_out";
  recorded_by: number;
  recorded_by_name: string;
  recorded_at: string;
  notes: string;
  evidence_photo: boolean;
}

export interface Property {
  id: number;
  name: string;
  location: string;
  cluster: string;
  total_units: number;
  occupied_units: number;
  monthly_rent: string;
  tag: string;
  status: string;
  occupancy_rate: number;
  photo_url: string;
  created_at: string;
}

export interface Unit {
  id: number;
  property: number;
  property_name: string;
  unit_number: string;
  unit_type: string;
  rent: string;
  status: string;
  tenant: string;
  created_at: string;
}

export interface Tenant {
  id: number;
  name: string;
  phone: string;
  property: number;
  property_name: string;
  unit: number | null;
  unit_number: string | null;
  lease_end: string;
  rent: string;
  status: string;
  account_linked: boolean;
  account_user_id: number | null;
  account_has_avatar: boolean;
  invitation_email: string;
  invitation_expires_at: string | null;
  created_at: string;
}

export interface Payment {
  id: number;
  reference: string;
  tenant: number;
  tenant_name: string;
  date: string;
  amount: number;
  method: string;
  match_status: string;
  created_at: string;
}

export interface Notice {
  id: number;
  icon: string;
  title: string;
  text: string;
  state: string;
  created_at: string;
}

export interface MaintenanceJob {
  id: number;
  job_id: string;
  property: number;
  property_name: string;
  unit: number | null;
  unit_number: string | null;
  issue: string;
  priority: string;
  reported_by: string;
  reported_by_user_id: number | null;
  reported_by_has_avatar: boolean;
  assignee: string;
  status: string;
  quote_amount: number | null;
  quote_notes: string;
  confirmation_photo_url: string;
  date: string;
}

export interface Staff {
  id: number;
  name: string;
  initials: string;
  role: string;
  email: string;
  roles: string[];
}

export interface DashboardStats {
  total_properties: number;
  total_tenants: number;
  rental_income: string;
  expenses: string;
  occupied_units: number;
  vacant_units: number;
  active_leases: number;
}

export const authAPI = {
  login: (credentials: LoginCredentials) => api.post<AuthResponse>("/auth/login/", credentials),
  register: (data: RegisterData) => api.post<RegisterResponse>("/auth/register/", data),
  me: () => api.get<User>("/auth/me/"),
  updateProfile: (data: Pick<User, "username" | "phone"> & { avatar_image?: File }) => {
    if (!data.avatar_image) {
      return api.patch<User>("/auth/me/", { username: data.username, phone: data.phone });
    }
    const form = new FormData();
    form.append("username", data.username);
    form.append("phone", data.phone);
    form.append("avatar_image", data.avatar_image);
    return api.patch<User>("/auth/me/", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  changePassword: (data: { current_password: string; new_password: string; confirm_password: string }) =>
    api.post<{ message: string }>("/auth/password/change/", data),
  requestPasswordReset: (email: string) =>
    api.post<{ message: string }>("/auth/password/reset/", { email }),
  confirmPasswordReset: (data: { uid: string; token: string; new_password: string; confirm_password: string }) =>
    api.post<{ message: string }>("/auth/password/reset/confirm/", data),
};

export const dashboardAPI = {
  stats: () => api.get<DashboardStats>("/dashboard/stats/"),
};

export const propertiesAPI = {
  list: () => api.get<Property[]>("/properties/"),
  create: (data: Partial<Property>) => api.post<Property>("/properties/", data),
  detail: (id: number) => api.get<Property>(`/properties/${id}/`),
  update: (id: number, data: Partial<Property>) => api.put<Property>(`/properties/${id}/`, data),
  remove: (id: number) => api.delete<void>(`/properties/${id}/`),
};

export const unitsAPI = {
  list: () => api.get<Unit[]>("/units/"),
  create: (data: Partial<Unit>) => api.post<Unit>("/units/", data),
};

export const tenantsAPI = {
  list: () => api.get<Tenant[]>("/tenants/"),
  create: (data: Partial<Tenant> & { account_email?: string }) => api.post<Tenant>("/tenants/", data),
  invite: (id: number, email: string) => api.post<TenantInvitation>(`/tenants/${id}/invite/`, { email }),
};

export const tenantInvitationsAPI = {
  details: (token: string) => api.get<TenantInvitationDetails>(`/tenant-invitations/${encodeURIComponent(token)}/`),
};

export const paymentsAPI = {
  list: () => api.get<Payment[]>("/payments/"),
  create: (data: Partial<Payment>) => api.post<Payment>("/payments/", data),
};

export const noticesAPI = {
  list: () => api.get<Notice[]>("/notices/"),
  create: (data: Partial<Notice>) => api.post<Notice>("/notices/", data),
  unreadCount: () => api.get<{ unread_count: number }>("/notices/unread-count/"),
};

export const maintenanceAPI = {
  list: () => api.get<MaintenanceJob[]>("/maintenance/"),
  create: (data: Partial<MaintenanceJob>) => api.post<MaintenanceJob>("/maintenance/", data),
  update: (id: number, data: Partial<MaintenanceJob>) => api.patch<MaintenanceJob>(`/maintenance/${id}/`, data),
};

export const staffAPI = {
  list: () => api.get<Staff[]>("/staff/"),
  create: (data: Partial<Staff>) => api.post<Staff>("/staff/", data),
};

export const usersAPI = {
  list: () => api.get<UserAccess[]>("/users/"),
  assignmentOptions: () => api.get<UserAssignmentOptions>("/users/assignment-options/"),
  avatar: (id: number) => api.get<Blob>(`/users/${id}/avatar/`, { responseType: "blob" }),
  profile: (id: number) => api.get<PublicUser>(`/users/${id}/profile/`),
  update: (id: number, data: Partial<Pick<UserAccess, "role" | "property_cluster" | "is_active_user" | "assigned_units" | "managed_property_ids">> & { managed_properties?: number[] }) =>
    api.patch<UserAccess>(`/users/${id}/`, data),
};

export const teamAPI = {
  onboard: (data: OnboardTeamMember) => api.post<UserAccess>("/team/onboarding/", data),
};

export const communicationAPI = {
  contacts: () => api.get<CommunicationContact[]>("/communication/contacts/"),
  conversations: () => api.get<Conversation[]>("/communication/conversations/"),
  startConversation: (data: { recipient: number; subject: string; body: string }) =>
    api.post<Conversation>("/communication/conversations/", data),
  messages: (conversationId: number) =>
    api.get<Message[]>(`/communication/conversations/${conversationId}/messages/`),
  sendMessage: (conversationId: number, body: string) =>
    api.post<Message>(`/communication/conversations/${conversationId}/messages/`, { body }),
};

export const tenancyEventsAPI = {
  list: () => api.get<TenancyEvent[]>("/tenancy-events/"),
  create: (data: Pick<TenancyEvent, "tenant" | "unit" | "action"> & { notes?: string; evidence_upload?: File }) => {
    const form = new FormData();
    form.append("tenant", String(data.tenant));
    form.append("unit", String(data.unit));
    form.append("action", data.action);
    if (data.notes) form.append("notes", data.notes);
    if (data.evidence_upload) form.append("evidence_upload", data.evidence_upload);
    return api.post<TenancyEvent>("/tenancy-events/", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  photo: (id: number) => api.get<Blob>(`/tenancy-events/${id}/photo/`, { responseType: "blob" }),
};

export interface Expense {
  id: number;
  title: string;
  category: string;
  amount: number;
  property: number | null;
  property_name: string | null;
  description: string;
  date: string;
  receipt_url: string;
  created_at: string;
}

export interface UnitInspection {
  id: number;
  unit: number;
  unit_number: string;
  property_name: string;
  inspection_type: "routine" | "move_in" | "move_out";
  inspector_name: string;
  inspection_date: string;
  condition: string;
  checklist: Record<string, string>;
  notes: string;
  issues_found: string;
  recommended_actions: string;
  next_inspection_date: string | null;
  created_at: string;
}

export const expensesAPI = {
  list: () => api.get<Expense[]>("/expenses/"),
  create: (data: Partial<Expense>) => api.post<Expense>("/expenses/", data),
  detail: (id: number) => api.get<Expense>(`/expenses/${id}/`),
  update: (id: number, data: Partial<Expense>) => api.put<Expense>(`/expenses/${id}/`, data),
  remove: (id: number) => api.delete<void>(`/expenses/${id}/`),
};

export const unitInspectionsAPI = {
  list: () => api.get<UnitInspection[]>("/unit-inspections/"),
  create: (data: Partial<UnitInspection>) => api.post<UnitInspection>("/unit-inspections/", data),
  detail: (id: number) => api.get<UnitInspection>(`/unit-inspections/${id}/`),
  update: (id: number, data: Partial<UnitInspection>) => api.put<UnitInspection>(`/unit-inspections/${id}/`, data),
  remove: (id: number) => api.delete<void>(`/unit-inspections/${id}/`),
};

export const healthAPI = {
  check: () => api.get("/health/"),
};
