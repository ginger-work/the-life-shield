/**
 * The Life Shield — API Client
 * Typed wrapper around all backend endpoints.
 */

// Use local proxy to avoid CORS issues with Railway CDN
const API_BASE = "/api/proxy";

type FetchOptions = RequestInit & { token?: string };

async function fetchAPI<T>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string> || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else {
    // Try to get token from localStorage in browser
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("access_token");
      if (stored) headers["Authorization"] = `Bearer ${stored}`;
    }
  }

  const response = await fetch(`${API_BASE}?path=${encodeURIComponent(path)}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json();
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  role: string;
}

export interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  status: string;
  sms_consent: boolean;
  email_consent: boolean;
  created_at: string;
}

export interface ClientProfile {
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  subscription_plan?: string;
  status: string;
  address?: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;
    zip?: string;
  };
  sms_consent: boolean;
  email_consent: boolean;
  voice_consent: boolean;
  created_at: string;
}

export interface CreditReport {
  bureau: string;
  score: number;
  pulled_at: string;
  report_date?: string;
}

export interface CreditItem {
  id: string;
  type: string;
  creditor: string;
  amount?: number;
  status: string;
  date?: string;
  bureau?: string;
}

export interface DisputeCase {
  id: string;
  status: string;
  bureau: string;
  dispute_reason: string;
  created_at: string;
  investigation_deadline?: string;
  outcome?: string;
}

export interface ChatMessage {
  id: string;
  direction: "inbound" | "outbound";
  content: string;
  channel: string;
  created_at: string;
  agent?: string;
}

export interface Appointment {
  id: string;
  type: string;
  scheduled_at: string;
  meeting_type: string;
  status: string;
  notes?: string;
}

export interface Document {
  id: string;
  name: string;
  category: string;
  status: string;
  uploaded_at: string;
}

export interface SubscriptionPlan {
  id: string;
  name: string;
  price_monthly: number;
  features: string[];
}

export interface Subscription {
  id: string;
  plan_id: string;
  plan_name: string;
  price_monthly: number;
  status: string;
  started_at?: string;
  next_billing_at?: string;
  features: string[];
}

export interface Payment {
  id: string;
  amount: number;
  description: string;
  status: string;
  paid_at?: string;
}

// ─── API Methods ──────────────────────────────────────────────────────────────

export const api = {
  auth: {
    login: (email: string, password: string) =>
      fetchAPI<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),

    register: (data: {
      email: string;
      password: string;
      first_name: string;
      last_name: string;
      sms_consent?: boolean;
      email_consent?: boolean;
    }) =>
      fetchAPI<TokenResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    refresh: (refresh_token: string) =>
      fetchAPI<TokenResponse>("/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token }),
      }),

    logout: () =>
      fetchAPI<void>("/auth/logout", { method: "POST" }),

    me: () => fetchAPI<UserProfile>("/auth/me"),

    forgotPassword: (email: string) =>
      fetchAPI<{ message: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
  },

  clients: {
    getProfile: () => fetchAPI<ClientProfile>("/clients/me"),

    updateProfile: (data: Partial<ClientProfile>) =>
      fetchAPI<ClientProfile>("/clients/me", {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    getDashboard: () =>
      fetchAPI<{
        success: boolean;
        data: {
          scores: Record<string, { score: number; pulled_at: string }>;
          active_disputes: number;
          resolved_disputes: number;
          next_appointment?: Appointment;
          recent_activity: Array<{
            id: string;
            channel: string;
            summary: string;
            created_at: string;
          }>;
          documents_pending: number;
          subscription?: { plan: string; status: string };
        };
      }>("/clients/me/dashboard"),

    updateConsent: (data: {
      sms_consent?: boolean;
      email_consent?: boolean;
      voice_consent?: boolean;
    }) =>
      fetchAPI<{ success: boolean }>("/clients/me/consent", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    listDocuments: () =>
      fetchAPI<{ success: boolean; documents: Document[] }>("/clients/me/documents"),

    deleteDocument: (docId: string) =>
      fetchAPI<void>(`/clients/me/documents/${docId}`, { method: "DELETE" }),

    listAppointments: () =>
      fetchAPI<{ success: boolean; appointments: Appointment[] }>("/clients/me/appointments"),

    bookAppointment: (data: {
      session_type: string;
      scheduled_at: string;
      meeting_type: string;
      notes?: string;
    }) =>
      fetchAPI<{ success: boolean; appointment_id: string }>("/clients/me/appointments", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    cancelAppointment: (aptId: string) =>
      fetchAPI<void>(`/clients/me/appointments/${aptId}`, { method: "DELETE" }),
  },

  credit: {
    getSummary: (clientId?: string) =>
      fetchAPI<{
        success: boolean;
        client_id: string;
        scores: CreditReport[];
        open_dispute_count: number;
        score_trend: string;
      }>("/credit/summary"),

    getReport: (clientId?: string) =>
      fetchAPI<{
        success: boolean;
        reports: CreditReport[];
      }>("/credit/reports"),

    getHistory: (days: number = 90) =>
      fetchAPI<{
        success: boolean;
        history: Array<{
          date: string;
          equifax?: number;
          experian?: number;
          transunion?: number;
          average?: number;
        }>;
      }>(`/credit/score-history?days=${days}`),

    getItems: () =>
      fetchAPI<{
        success: boolean;
        tradelines: CreditItem[];
        inquiries: CreditItem[];
        negative_items: CreditItem[];
      }>("/credit/tradelines"),

    pullReport: () =>
      fetchAPI<{ success: boolean; message: string }>("/credit/soft-pull", {
        method: "POST",
        body: JSON.stringify({}),
      }),
  },

  disputes: {
    list: () =>
      fetchAPI<{
        success: boolean;
        disputes: DisputeCase[];
        total: number;
      }>("/disputes"),

    create: (data: {
      tradeline_id: string;
      bureau: string;
      dispute_reason: string;
      client_statement?: string;
    }) =>
      fetchAPI<{ success: boolean; dispute_id: string }>("/disputes", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    getStatus: (disputeId: string) =>
      fetchAPI<{
        success: boolean;
        dispute: DisputeCase;
        letter?: { content: string; status: string };
        bureau_responses: Array<{
          bureau: string;
          response_date: string;
          outcome: string;
          summary?: string;
        }>;
      }>(`/disputes/${disputeId}`),

    approveLetter: (disputeId: string, approved: boolean, notes?: string) =>
      fetchAPI<{ success: boolean }>(`/disputes/${disputeId}/approve-letter`, {
        method: "POST",
        body: JSON.stringify({ approved, notes }),
      }),
  },

  agents: {
    chat: (message: string, channel: string = "portal_chat") =>
      fetchAPI<{
        success: boolean;
        agent: string;
        response: string;
        channel: string;
        requires_human: boolean;
        timestamp: string;
      }>("/agents/chat", {
        method: "POST",
        body: JSON.stringify({ message, channel }),
      }),

    getHistory: (clientId: string, limit: number = 50, offset: number = 0) =>
      fetchAPI<{
        success: boolean;
        messages: ChatMessage[];
        total: number;
      }>(`/agents/history/${clientId}?limit=${limit}&offset=${offset}`),

    getStatus: () =>
      fetchAPI<{
        agent: string;
        status: string;
        expected_response_time: string;
        channels: string[];
        disclosure: string;
      }>("/agents/status"),

    escalate: (reason: string, message?: string) =>
      fetchAPI<{ success: boolean; escalation_id?: string; message: string }>(
        "/agents/escalate",
        {
          method: "POST",
          body: JSON.stringify({ reason, message }),
        }
      ),
  },

  products: {
    listPlans: () =>
      fetchAPI<{ success: boolean; plans: SubscriptionPlan[] }>(
        "/products/subscriptions/plans"
      ),

    getMySubscription: () =>
      fetchAPI<{ success: boolean; subscription: Subscription | null }>(
        "/products/subscriptions/mine"
      ),

    subscribe: (plan_id: string, payment_token: string) =>
      fetchAPI<{ success: boolean; subscription_id: string }>("/products/subscriptions", {
        method: "POST",
        body: JSON.stringify({ plan_id, payment_token }),
      }),

    cancelSubscription: (subscriptionId: string, reason?: string) =>
      fetchAPI<{ success: boolean; message: string }>(
        `/products/subscriptions/${subscriptionId}?reason=${reason || ""}`,
        { method: "DELETE" }
      ),

    getBillingHistory: (limit: number = 20) =>
      fetchAPI<{ success: boolean; payments: Payment[]; total: number }>(
        `/products/billing/history?limit=${limit}`
      ),

    listProducts: () =>
      fetchAPI<{
        success: boolean;
        products: Array<{
          id: string;
          name: string;
          description: string;
          price: number;
          category: string;
        }>;
      }>("/products"),
  },
};

// ─── Auth helpers ─────────────────────────────────────────────────────────────

export function saveTokens(response: TokenResponse) {
  if (typeof window === "undefined") return;
  localStorage.setItem("access_token", response.access_token);
  localStorage.setItem("refresh_token", response.refresh_token);
  localStorage.setItem("user_id", response.user_id);
  localStorage.setItem("role", response.role);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user_id");
  localStorage.removeItem("role");
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export function isAuthenticated(): boolean {
  return !!getStoredToken();
}
