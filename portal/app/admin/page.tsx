"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AdminStats {
  total_clients: number;
  active_clients: number;
  new_clients_this_month: number;
  churn_rate_pct: number;
  disputes_filed_this_month: number;
  disputes_resolved_this_month: number;
  dispute_success_rate_pct: number;
  items_removed_total: number;
  mrr: number;
  total_revenue_this_month: number;
  compliance_alerts_open: number;
  escalations_pending: number;
  messages_sent_today: number;
  calls_today: number;
  generated_at: string;
}

interface Client {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  status: string;
  subscription_plan: string;
  created_at: string;
  active_disputes: number;
  score_improvement?: number;
  lifecycle_state?: string;
}

interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  trigger: string;
  day: number;
}

// ─── Admin Auth Guard ─────────────────────────────────────────────────────────

function useAdminAuth() {
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const router = useRouter();

  useEffect(() => {
    const role = typeof window !== "undefined" ? localStorage.getItem("role") : null;
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token || role !== "admin") {
      router.replace("/login");
      setAuthorized(false);
    } else {
      setAuthorized(true);
    }
  }, [router]);

  return authorized;
}

// ─── Icon Components ──────────────────────────────────────────────────────────

function IconUsers() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  );
}

function IconDollar() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function IconDisputes() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
    </svg>
  );
}

function IconAlert() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}

function IconMail() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, icon, color = "navy" }: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ReactNode;
  color?: "navy" | "gold" | "teal" | "red";
}) {
  const colorMap = {
    navy: "bg-[#1a2744] text-white",
    gold: "bg-[#c4922a] text-white",
    teal: "bg-[#0d7a6e] text-white",
    red: "bg-red-600 text-white",
  };

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <p className="text-gray-500 text-xs font-medium uppercase tracking-wide">{label}</p>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
          {icon}
        </div>
      </div>
      <p className="text-2xl font-bold text-[#1a2744]">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Mock Data ────────────────────────────────────────────────────────────────

const MOCK_STATS: AdminStats = {
  total_clients: 0,
  active_clients: 0,
  new_clients_this_month: 0,
  churn_rate_pct: 0,
  disputes_filed_this_month: 0,
  disputes_resolved_this_month: 0,
  dispute_success_rate_pct: 0,
  items_removed_total: 0,
  mrr: 0,
  total_revenue_this_month: 0,
  compliance_alerts_open: 0,
  escalations_pending: 0,
  messages_sent_today: 0,
  calls_today: 0,
  generated_at: new Date().toISOString(),
};

const EMAIL_TEMPLATES: EmailTemplate[] = [
  { id: "welcome", name: "Welcome Email", subject: "Welcome to The Life Shield", trigger: "on_signup", day: 0 },
  { id: "tim-welcome", name: "Welcome from Tim", subject: "Hi, I'm Tim Shaw — your credit advisor", trigger: "day_0", day: 0 },
  { id: "credit-pulled", name: "Credit Pull Complete", subject: "Your credit report is ready", trigger: "day_1", day: 1 },
  { id: "findings", name: "Here's What We Found", subject: "We found things to dispute on your report", trigger: "day_3", day: 3 },
  { id: "dispute-filed", name: "Dispute Filed", subject: "Your dispute has been filed with the bureaus", trigger: "day_7", day: 7 },
  { id: "monthly-checkin", name: "Monthly Check-In", subject: "Your 30-day credit progress report", trigger: "day_30", day: 30 },
];

const LIFECYCLE_STATES = ["All", "New", "Active", "Engaged", "Inactive"];

// ─── Dashboard Tab ────────────────────────────────────────────────────────────

function DashboardTab({ stats }: { stats: AdminStats }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[#1a2744] mb-4">Key Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Clients"
            value={stats.total_clients}
            sub={`${stats.active_clients} active`}
            icon={<IconUsers />}
            color="navy"
          />
          <StatCard
            label="Monthly Revenue"
            value={`$${stats.total_revenue_this_month.toFixed(0)}`}
            sub={`MRR: $${stats.mrr.toFixed(0)}`}
            icon={<IconDollar />}
            color="gold"
          />
          <StatCard
            label="Disputes This Month"
            value={stats.disputes_filed_this_month}
            sub={`${stats.dispute_success_rate_pct.toFixed(0)}% success rate`}
            icon={<IconDisputes />}
            color="teal"
          />
          <StatCard
            label="Open Alerts"
            value={stats.compliance_alerts_open}
            sub={`${stats.escalations_pending} pending escalations`}
            icon={<IconAlert />}
            color={stats.compliance_alerts_open > 0 ? "red" : "navy"}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Client breakdown */}
        <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
          <h3 className="font-semibold text-[#1a2744] text-sm mb-4">Client Lifecycle</h3>
          <div className="space-y-3">
            {[
              { label: "New (0–7 days)", count: 0, color: "bg-blue-400" },
              { label: "Active (7–30 days)", count: 0, color: "bg-[#c4922a]" },
              { label: "Engaged (30+ days)", count: 0, color: "bg-[#0d7a6e]" },
              { label: "Inactive", count: 0, color: "bg-gray-300" },
            ].map((row, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className={`w-2.5 h-2.5 rounded-full ${row.color} flex-shrink-0`} />
                <span className="text-sm text-gray-600 flex-1">{row.label}</span>
                <span className="text-sm font-semibold text-[#1a2744]">{row.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tim Shaw Performance */}
        <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
          <h3 className="font-semibold text-[#1a2744] text-sm mb-4">Tim Shaw — Agent Stats</h3>
          <div className="space-y-3">
            {[
              { label: "Clients Assigned", value: "0" },
              { label: "Cases In Progress", value: "0" },
              { label: "Disputes Filed", value: stats.disputes_filed_this_month },
              { label: "Disputes Resolved", value: stats.disputes_resolved_this_month },
              { label: "Items Removed Total", value: stats.items_removed_total },
              { label: "Messages Today", value: stats.messages_sent_today },
            ].map((row, i) => (
              <div key={i} className="flex items-center justify-between">
                <span className="text-sm text-gray-600">{row.label}</span>
                <span className="text-sm font-semibold text-[#1a2744]">{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Revenue breakdown */}
      <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
        <h3 className="font-semibold text-[#1a2744] text-sm mb-4">Revenue Breakdown</h3>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-4">
          {[
            { label: "Free Plan", count: 0, revenue: "$0" },
            { label: "Professional ($69)", count: 0, revenue: "$0" },
            { label: "Elite ($129)", count: 0, revenue: "$0" },
            { label: "Churn Rate", count: null, revenue: `${stats.churn_rate_pct.toFixed(1)}%` },
            { label: "New This Month", count: stats.new_clients_this_month, revenue: null },
          ].map((col, i) => (
            <div key={i} className="text-center bg-[#f4f6f9] rounded-lg p-3">
              <p className="text-xs text-gray-400 mb-1">{col.label}</p>
              {col.revenue && <p className="font-bold text-[#1a2744] text-sm">{col.revenue}</p>}
              {col.count !== null && col.count !== undefined && (
                <p className="font-bold text-[#1a2744] text-sm">{col.count}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Clients Tab ──────────────────────────────────────────────────────────────

function ClientsTab() {
  const [clients, setClients] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState("All");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Client | null>(null);

  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(
        `/api/admin/clients?per_page=100${lifecycle !== "All" ? `&status_filter=${lifecycle.toLowerCase()}` : ""}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await res.json();
      setClients(data.clients || []);
    } catch {
      setClients([]);
    } finally {
      setLoading(false);
    }
  }, [lifecycle]);

  useEffect(() => { loadClients(); }, [loadClients]);

  const filtered = clients.filter((c) => {
    const q = search.toLowerCase();
    return !q || c.email.toLowerCase().includes(q) ||
      `${c.first_name} ${c.last_name}`.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <IconSearch />
          </span>
          <input
            type="text"
            placeholder="Search by email or name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
          />
        </div>
        <div className="flex gap-2">
          {LIFECYCLE_STATES.map((s) => (
            <button
              key={s}
              onClick={() => setLifecycle(s)}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                lifecycle === s
                  ? "bg-[#1a2744] text-white"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex justify-center items-center py-16">
            <div className="animate-spin w-6 h-6 border-4 border-[#c4922a] border-t-transparent rounded-full" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-16">
            <p className="font-medium text-sm">No clients found</p>
            <p className="text-xs mt-1">Clients will appear here once they register.</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-[#f4f6f9] border-b border-gray-100">
              <tr>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Client</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Plan</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Disputes</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setSelected(c)}
                  className="hover:bg-[#f4f6f9] cursor-pointer transition-colors"
                >
                  <td className="px-5 py-4">
                    <p className="font-medium text-[#1a2744] text-sm">{c.first_name} {c.last_name}</p>
                    <p className="text-xs text-gray-400">{c.email}</p>
                  </td>
                  <td className="px-5 py-4 hidden md:table-cell">
                    <span className="text-xs bg-[#f4f6f9] text-[#1a2744] px-2 py-1 rounded-md font-medium capitalize">
                      {c.subscription_plan || "free"}
                    </span>
                  </td>
                  <td className="px-5 py-4 hidden lg:table-cell">
                    <span className="text-sm text-gray-600">{c.active_disputes ?? 0} active</span>
                  </td>
                  <td className="px-5 py-4">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      c.status === "active" ? "bg-green-100 text-green-700" :
                      c.status === "suspended" ? "bg-red-100 text-red-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="px-5 py-4 hidden lg:table-cell text-xs text-gray-400">
                    {c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Client detail modal */}
      {selected && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="bg-white rounded-2xl p-7 max-w-md w-full shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-[#1a2744] text-lg">
                {selected.first_name} {selected.last_name}
              </h3>
              <button
                onClick={() => setSelected(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>
            <div className="space-y-3 text-sm">
              {[
                ["Email", selected.email],
                ["Plan", selected.subscription_plan || "Free"],
                ["Status", selected.status],
                ["Active Disputes", selected.active_disputes ?? 0],
                ["Lifecycle", selected.lifecycle_state || "Unknown"],
                ["Joined", selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">{label}</span>
                  <span className="font-medium text-[#1a2744]">{value}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 flex gap-3">
              <button className="flex-1 bg-[#1a2744] text-white py-2.5 rounded-lg text-sm font-medium hover:bg-[#243358]">
                View Full Profile
              </button>
              <button
                onClick={() => setSelected(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg text-sm font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Email Campaigns Tab ──────────────────────────────────────────────────────

function EmailTab() {
  const [sending, setSending] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [segment, setSegment] = useState("all");
  const [bulkSubject, setBulkSubject] = useState("");
  const [bulkBody, setBulkBody] = useState("");
  const [sendingBulk, setSendingBulk] = useState(false);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  async function sendTestEmail(templateId: string) {
    setSending(templateId);
    try {
      const token = localStorage.getItem("access_token");
      await fetch("/api/email/test", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ template_id: templateId }),
      });
      showToast("Test email sent successfully.");
    } catch {
      showToast("Email service not yet configured. Add SENDGRID_API_KEY to environment.");
    } finally {
      setSending(null);
    }
  }

  async function sendBulk() {
    if (!bulkSubject.trim() || !bulkBody.trim()) {
      showToast("Subject and message are required.");
      return;
    }
    setSendingBulk(true);
    try {
      const token = localStorage.getItem("access_token");
      await fetch("/api/email/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ segment, subject: bulkSubject, body: bulkBody }),
      });
      showToast("Bulk email queued successfully.");
      setBulkSubject("");
      setBulkBody("");
    } catch {
      showToast("Email service not yet configured.");
    } finally {
      setSendingBulk(false);
    }
  }

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-[#1a2744] text-white px-5 py-3 rounded-xl shadow-lg text-sm font-medium">
          {toast}
        </div>
      )}

      {/* Email templates */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-[#1a2744]">Lifecycle Email Templates</h3>
          <p className="text-xs text-gray-400 mt-0.5">Automated emails triggered by client lifecycle events</p>
        </div>
        <div className="divide-y divide-gray-50">
          {EMAIL_TEMPLATES.map((tmpl) => (
            <div key={tmpl.id} className="flex items-center justify-between px-5 py-4">
              <div>
                <p className="font-medium text-[#1a2744] text-sm">{tmpl.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{tmpl.subject}</p>
                <span className="inline-block mt-1 text-xs bg-[#f4f6f9] text-[#1a2744] px-2 py-0.5 rounded-md">
                  Trigger: {tmpl.trigger} {tmpl.day > 0 ? `(Day ${tmpl.day})` : "(Immediate)"}
                </span>
              </div>
              <button
                onClick={() => sendTestEmail(tmpl.id)}
                disabled={sending === tmpl.id}
                className="text-xs bg-[#1a2744] text-white px-3 py-1.5 rounded-lg hover:bg-[#243358] disabled:opacity-50 font-medium"
              >
                {sending === tmpl.id ? "Sending…" : "Send Test"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Bulk email compose */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm p-6">
        <h3 className="font-semibold text-[#1a2744] mb-4">Send Bulk Email</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Segment</label>
            <select
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
            >
              <option value="all">All Clients</option>
              <option value="new">New (0–7 days)</option>
              <option value="active">Active (7–30 days)</option>
              <option value="engaged">Engaged (30+ days)</option>
              <option value="inactive">Inactive</option>
              <option value="free">Free Plan</option>
              <option value="professional">Professional Plan</option>
              <option value="elite">Elite Plan</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Subject</label>
            <input
              type="text"
              value={bulkSubject}
              onChange={(e) => setBulkSubject(e.target.value)}
              placeholder="Email subject line..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Message</label>
            <textarea
              value={bulkBody}
              onChange={(e) => setBulkBody(e.target.value)}
              placeholder="Write your message here..."
              rows={5}
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] resize-none"
            />
          </div>
          <button
            onClick={sendBulk}
            disabled={sendingBulk}
            className="bg-[#c4922a] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[#d9a84e] disabled:opacity-50"
          >
            {sendingBulk ? "Sending…" : "Send to Segment"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Admin Page ──────────────────────────────────────────────────────────

type Tab = "dashboard" | "clients" | "email";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Dashboard", icon: <IconShield /> },
  { id: "clients", label: "Clients", icon: <IconUsers /> },
  { id: "email", label: "Email Campaigns", icon: <IconMail /> },
];

export default function AdminPage() {
  const authorized = useAdminAuth();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<AdminStats>(MOCK_STATS);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    if (!authorized) return;
    (async () => {
      setStatsLoading(true);
      try {
        const token = localStorage.getItem("access_token");
        const res = await fetch("/api/admin/dashboard", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setStats(data);
        }
      } catch {
        // Use mock data
      } finally {
        setStatsLoading(false);
      }
    })();
  }, [authorized]);

  if (authorized === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f6f9]">
        <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!authorized) return null;

  return (
    <div className="min-h-screen bg-[#f4f6f9]">
      {/* Header */}
      <div className="bg-[#1a2744] text-white px-6 py-4 shadow-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#c4922a] rounded-lg flex items-center justify-center">
              <IconShield />
            </div>
            <div>
              <h1 className="font-bold text-base">The Life Shield</h1>
              <p className="text-[#6b84b0] text-xs">Admin Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-[#6b84b0]">
              Updated {new Date(stats.generated_at).toLocaleTimeString()}
            </span>
            <a href="/dashboard" className="text-[#8899bb] hover:text-white text-xs">
              Back to Portal
            </a>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Tabs */}
        <div className="flex gap-1 bg-white border border-gray-100 rounded-xl p-1 shadow-sm mb-6 w-fit">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === t.id
                  ? "bg-[#1a2744] text-white shadow-sm"
                  : "text-gray-500 hover:text-[#1a2744]"
              }`}
            >
              <span className="w-4 h-4">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {statsLoading && tab === "dashboard" ? (
          <div className="flex justify-center items-center py-20">
            <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full" />
          </div>
        ) : (
          <>
            {tab === "dashboard" && <DashboardTab stats={stats} />}
            {tab === "clients" && <ClientsTab />}
            {tab === "email" && <EmailTab />}
          </>
        )}
      </div>
    </div>
  );
}
