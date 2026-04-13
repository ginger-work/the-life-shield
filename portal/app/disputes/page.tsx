"use client";

import { useState, useEffect } from "react";
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
  removed: { color: "bg-green-100 text-green-700", label: "✓ Removed" },
  updated: { color: "bg-yellow-100 text-yellow-700", label: "⟳ Updated" },
  verified: { color: "bg-red-100 text-red-700", label: "✗ Verified" },
  pending: { color: "bg-blue-100 text-blue-700", label: "⧗ Pending" },
};

export default function DisputesPage() {
  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<DisputeCase | null>(null);

  useEffect(() => {
    api.disputes.list()
      .then((res) => setDisputes(res.disputes || []))
      .catch(() => {
        // Mock data
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
      })
      .finally(() => setLoading(false));
  }, []);

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
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
              {disputes.length} Total Disputes
            </h2>
            <a
              href="/credit"
              className="bg-[#c4922a] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#d9a84e] transition-colors"
            >
              + New Dispute
            </a>
          </div>

          {loading && (
            <div className="text-center py-12">
              <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full mx-auto" />
            </div>
          )}

          {!loading && disputes.length === 0 && (
            <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-gray-100">
              <p className="text-4xl mb-3">⚖️</p>
              <p className="text-[#1a2744] font-semibold">No disputes yet</p>
              <p className="text-gray-500 text-sm mt-1">View your credit report to identify items to dispute.</p>
              <a href="/credit" className="text-[#c4922a] text-sm mt-3 inline-block hover:underline">
                View Credit Report →
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
                onClick={() => setSelected(dispute)}
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
                  <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p className="text-sm text-yellow-800 font-medium">📋 Your approval is required</p>
                    <p className="text-xs text-yellow-700 mt-1">Review and approve the dispute letter before it can be filed.</p>
                    <button
                      className="mt-2 bg-yellow-600 text-white px-4 py-2 rounded-lg text-xs font-semibold hover:bg-yellow-700"
                      onClick={(e) => { e.stopPropagation(); }}
                    >
                      Review & Approve Letter
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </main>
      </div>
    </div>
  );
}
