"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { DisputeTimeline } from "@/components/ui/DisputeTimeline";
import { api, DisputeCase } from "@/lib/api";

const STATUS_BADGE: Record<string, { color: string; label: string }> = {
  pending_approval: { color: "bg-yellow-100 text-yellow-700", label: "Needs Approval" },
  approved: { color: "bg-blue-100 text-blue-700", label: "Approved" },
  filed: { color: "bg-indigo-100 text-indigo-700", label: "Filed" },
  investigating: { color: "bg-purple-100 text-purple-700", label: "Investigating" },
  resolved: { color: "bg-green-100 text-green-700", label: "Resolved" },
  rejected: { color: "bg-red-100 text-red-700", label: "Rejected" },
  withdrawn: { color: "bg-gray-100 text-gray-700", label: "Withdrawn" },
};

const OUTCOME_BADGE: Record<string, { color: string; label: string }> = {
  removed: { color: "bg-green-100 text-green-700", label: "Removed" },
  updated: { color: "bg-yellow-100 text-yellow-700", label: "Updated" },
  verified: { color: "bg-red-100 text-red-700", label: "Verified" },
  pending: { color: "bg-blue-100 text-blue-700", label: "Pending" },
};

const DISPUTE_REASONS = [
  { value: "inaccurate", label: "Inaccurate Information" },
  { value: "not_mine", label: "Not My Account" },
  { value: "obsolete", label: "Obsolete / Too Old" },
  { value: "duplicate", label: "Duplicate Account" },
  { value: "identity_theft", label: "Identity Theft" },
  { value: "other", label: "Other" },
];

function DisputesContent() {
  const searchParams = useSearchParams();
  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<DisputeCase | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<{
    dispute: DisputeCase;
    letter?: { content: string; status: string };
  } | null>(null);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  // New dispute form
  const [showNewDispute, setShowNewDispute] = useState(false);
  const [filing, setFiling] = useState(false);
  const [newDispute, setNewDispute] = useState({
    tradeline_id: searchParams?.get("tradeline_id") || "",
    bureau: searchParams?.get("bureau") || "equifax",
    dispute_reason: "inaccurate",
    client_statement: "",
  });

  useEffect(() => {
    // Auto-open new dispute form if coming from credit page
    if (searchParams?.get("tradeline_id")) {
      setShowNewDispute(true);
    }
    loadDisputes();
  }, []);

  async function loadDisputes() {
    setLoading(true);
    try {
      const res = await api.disputesMgmt.getDisputes();
      setDisputes(res.disputes || []);
    } catch {
      setDisputes([
        {
          id: "d1",
          status: "investigating",
          bureau: "equifax",
          dispute_reason: "inaccurate",
          created_at: new Date(Date.now() - 86400000 * 15).toISOString(),
          investigation_deadline: new Date(Date.now() + 86400000 * 15).toISOString(),
          outcome: undefined,
        },
        {
          id: "d2",
          status: "pending_approval",
          bureau: "transunion",
          dispute_reason: "not_mine",
          created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
          investigation_deadline: new Date(Date.now() + 86400000 * 28).toISOString(),
          outcome: undefined,
        },
        {
          id: "d3",
          status: "resolved",
          bureau: "experian",
          dispute_reason: "obsolete",
          created_at: new Date(Date.now() - 86400000 * 45).toISOString(),
          investigation_deadline: new Date(Date.now() - 86400000 * 15).toISOString(),
          outcome: "removed",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function showToast(msg: string, type: "success" | "error") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function loadDisputeDetail(id: string) {
    try {
      const res = await api.disputesMgmt.getDisputeDetail(id);
      setSelectedDetail({ dispute: res.dispute, letter: res.letter });
    } catch {
      // Keep selected dispute without letter
    }
  }

  async function handleSelectDispute(dispute: DisputeCase) {
    setSelected(dispute);
    await loadDisputeDetail(dispute.id);
  }

  async function handleApproveLetter(disputeId: string, approved: boolean) {
    setApprovingId(disputeId);
    try {
      await api.disputesMgmt.approveLetter(disputeId, approved);
      showToast(approved ? "Letter approved! Dispute will be filed shortly." : "Letter rejected.", "success");
      await loadDisputes();
      setSelected(null);
      setSelectedDetail(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update letter";
      showToast(msg, "error");
    } finally {
      setApprovingId(null);
    }
  }

  async function handleFileDispute() {
    if (!newDispute.tradeline_id || !newDispute.bureau) {
      showToast("Please fill in all required fields", "error");
      return;
    }
    setFiling(true);
    try {
      await api.disputesMgmt.fileDispute(newDispute);
      showToast("Dispute filed successfully! We'll generate your dispute letter shortly.", "success");
      setShowNewDispute(false);
      setNewDispute({ tradeline_id: "", bureau: "equifax", dispute_reason: "inaccurate", client_statement: "" });
      await loadDisputes();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to file dispute";
      showToast(msg, "error");
    } finally {
      setFiling(false);
    }
  }

  function daysRemaining(deadline?: string): number {
    if (!deadline) return 0;
    return Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000));
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Disputes" />
        <main className="flex-1 p-6 space-y-4">
          {/* Toast */}
          {toast && (
            <div className={`fixed top-4 right-4 z-50 px-5 py-3 rounded-xl shadow-lg text-white font-medium text-sm ${
              toast.type === "success" ? "bg-green-600" : "bg-red-600"
            }`}>
              {toast.msg}
            </div>
          )}

          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
              {disputes.length} Total Disputes
            </h2>
            <button
              onClick={() => setShowNewDispute(true)}
              className="bg-[#c4922a] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#d9a84e] transition-colors"
            >
              + New Dispute
            </button>
          </div>

          {loading && (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full mx-auto" />
            </div>
          )}

          {!loading && disputes.length === 0 && (
            <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-gray-100">
              <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg width="22" height="22" fill="none" stroke="#6b7280" viewBox="0 0 24 24" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
                </svg>
              </div>
              <p className="text-[#1a2744] font-semibold">No disputes on record</p>
              <p className="text-gray-500 text-sm mt-1.5 leading-relaxed">Review your credit report to identify inaccuracies eligible for dispute.</p>
              <a href="/credit" className="text-[#c4922a] text-sm mt-3 inline-block hover:underline font-medium">
                View Credit Report
              </a>
            </div>
          )}

          {disputes.map((dispute) => {
            const statusInfo = STATUS_BADGE[dispute.status] || { color: "bg-gray-100 text-gray-700", label: dispute.status };
            const outcomeInfo = dispute.outcome ? OUTCOME_BADGE[dispute.outcome] : null;
            const days = daysRemaining(dispute.investigation_deadline);

            return (
              <div
                key={dispute.id}
                className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:border-[#c4922a]/30 transition-colors cursor-pointer"
                onClick={() => handleSelectDispute(dispute)}
              >
                {/* Header row */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${statusInfo.color}`}>
                      {statusInfo.label}
                    </span>
                    {outcomeInfo && (
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${outcomeInfo.color}`}>
                        {outcomeInfo.label}
                      </span>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-400 capitalize">{dispute.bureau}</p>
                    {days > 0 && dispute.status === "investigating" && (
                      <p className="text-xs text-orange-500">{days} days remaining</p>
                    )}
                  </div>
                </div>

                {/* Timeline */}
                <DisputeTimeline status={dispute.status} />

                {/* Investigation progress bar */}
                {dispute.status === "investigating" && dispute.investigation_deadline && (
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>Investigation progress</span>
                      <span>{days} days left</span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2">
                      <div
                        className="bg-[#c4922a] rounded-full h-2 transition-all"
                        style={{ width: `${Math.min(100, ((30 - days) / 30) * 100)}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Meta */}
                <div className="flex items-center gap-4 mt-4 text-xs text-gray-400">
                  <span>Reason: <span className="text-gray-600 capitalize">{dispute.dispute_reason?.replace(/_/g, " ")}</span></span>
                  <span>Filed: {new Date(dispute.created_at).toLocaleDateString()}</span>
                </div>

                {/* Approval CTA */}
                {dispute.status === "pending_approval" && (
                  <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm text-amber-800 font-semibold">Action Required — Letter Approval</p>
                    <p className="text-xs text-amber-700 mt-1 leading-relaxed">Please review and approve the dispute letter before it can be submitted to the credit bureau.</p>
                    <div className="mt-3 flex gap-2">
                      <button
                        className="bg-[#1a2744] text-white px-4 py-2 rounded-lg text-xs font-medium hover:bg-[#243358] disabled:opacity-50"
                        disabled={approvingId === dispute.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleApproveLetter(dispute.id, true);
                        }}
                      >
                        {approvingId === dispute.id ? "Approving..." : "Approve Letter"}
                      </button>
                      <button
                        className="border border-gray-300 text-gray-600 px-4 py-2 rounded-lg text-xs font-medium hover:bg-gray-50 disabled:opacity-50"
                        disabled={approvingId === dispute.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleApproveLetter(dispute.id, false);
                        }}
                      >
                        Request Revision
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </main>
      </div>

      {/* New Dispute Modal */}
      {showNewDispute && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-lg font-bold text-[#1a2744] mb-4">File New Dispute</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Account / Tradeline ID *</label>
                <input
                  type="text"
                  value={newDispute.tradeline_id}
                  onChange={(e) => setNewDispute({ ...newDispute, tradeline_id: e.target.value })}
                  placeholder="e.g. n1, t2, or account ID"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bureau *</label>
                <select
                  value={newDispute.bureau}
                  onChange={(e) => setNewDispute({ ...newDispute, bureau: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                >
                  <option value="equifax">Equifax</option>
                  <option value="experian">Experian</option>
                  <option value="transunion">TransUnion</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dispute Reason *</label>
                <select
                  value={newDispute.dispute_reason}
                  onChange={(e) => setNewDispute({ ...newDispute, dispute_reason: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                >
                  {DISPUTE_REASONS.map(r => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Your Statement (optional)</label>
                <textarea
                  value={newDispute.client_statement}
                  onChange={(e) => setNewDispute({ ...newDispute, client_statement: e.target.value })}
                  placeholder="Describe why this item should be disputed..."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm h-20 resize-none focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => setShowNewDispute(false)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleFileDispute}
                disabled={filing}
                className="flex-1 bg-[#c4922a] text-white py-2.5 rounded-lg font-medium hover:bg-[#d9a84e] disabled:opacity-50"
              >
                {filing ? "Filing…" : "File Dispute"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dispute Detail Modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-[#1a2744]">Dispute Detail</h3>
              <button onClick={() => { setSelected(null); setSelectedDetail(null); }} className="text-gray-400 hover:text-gray-600 p-1"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg></button>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex gap-2">
                <span className="text-gray-500 w-24">Status:</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                  (STATUS_BADGE[selected.status] || { color: "bg-gray-100 text-gray-700" }).color
                }`}>{(STATUS_BADGE[selected.status] || { label: selected.status }).label}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-500 w-24">Bureau:</span>
                <span className="capitalize">{selected.bureau}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-500 w-24">Reason:</span>
                <span className="capitalize">{selected.dispute_reason?.replace(/_/g, " ")}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-500 w-24">Filed:</span>
                <span>{new Date(selected.created_at).toLocaleDateString()}</span>
              </div>
              {selected.investigation_deadline && (
                <div className="flex gap-2">
                  <span className="text-gray-500 w-24">Deadline:</span>
                  <span>{new Date(selected.investigation_deadline).toLocaleDateString()}</span>
                </div>
              )}
              {selectedDetail?.letter && (
                <div className="mt-4">
                  <p className="font-semibold text-[#1a2744] mb-2">Dispute Letter</p>
                  <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-700 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {selectedDetail.letter.content}
                  </div>
                </div>
              )}
            </div>
            <button
              onClick={() => { setSelected(null); setSelectedDetail(null); }}
              className="mt-5 w-full border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DisputesPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full" />
        </div>
      </div>
    }>
      <DisputesContent />
    </Suspense>
  );
}
