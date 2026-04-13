"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { api } from "@/lib/api";

interface DashboardData {
  scores: Record<string, { score: number; pulled_at: string }>;
  active_disputes: number;
  resolved_disputes: number;
  next_appointment?: {
    id: string;
    type: string;
    scheduled_at: string;
    meeting_type: string;
  };
  recent_activity: Array<{
    id: string;
    channel: string;
    summary: string;
    created_at: string;
  }>;
  documents_pending: number;
  subscription?: { plan: string; status: string };
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.clients.getDashboard()
      .then((res) => setData(res.data))
      .catch(() => {
        // Mock data for demo
        setData({
          scores: {
            equifax: { score: 652, pulled_at: new Date().toISOString() },
            experian: { score: 671, pulled_at: new Date().toISOString() },
            transunion: { score: 644, pulled_at: new Date().toISOString() },
          },
          active_disputes: 3,
          resolved_disputes: 7,
          next_appointment: {
            id: "1",
            type: "credit_coaching",
            scheduled_at: new Date(Date.now() + 86400000 * 2).toISOString(),
            meeting_type: "video",
          },
          recent_activity: [
            { id: "1", channel: "portal_chat", summary: "Tim Shaw provided dispute status update", created_at: new Date().toISOString() },
            { id: "2", channel: "email", summary: "Credit report analysis completed", created_at: new Date(Date.now() - 3600000).toISOString() },
          ],
          documents_pending: 1,
          subscription: { plan: "premium", status: "active" },
        });
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Dashboard" scores={data?.scores} />

        <main className="flex-1 p-6 space-y-6">
          {/* Score gauges */}
          <section className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
            <h2 className="text-sm font-semibold text-[#1a2744] uppercase tracking-wide mb-4">Credit Scores</h2>
            <div className="flex gap-8 justify-center flex-wrap">
              {Object.entries(data?.scores || {}).map(([bureau, info]) => (
                <ScoreGauge
                  key={bureau}
                  score={info.score}
                  bureau={bureau}
                  pulledAt={info.pulled_at}
                  size={140}
                />
              ))}
            </div>
          </section>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Active Disputes</p>
              <p className="text-3xl font-bold text-[#1a2744] mt-1">{data?.active_disputes ?? 0}</p>
              <p className="text-xs text-orange-500 mt-1">Under investigation</p>
            </div>
            <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Resolved</p>
              <p className="text-3xl font-bold text-green-600 mt-1">{data?.resolved_disputes ?? 0}</p>
              <p className="text-xs text-green-500 mt-1">Items removed or updated</p>
            </div>
            <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Documents</p>
              <p className="text-3xl font-bold text-[#1a2744] mt-1">{data?.documents_pending ?? 0}</p>
              <p className="text-xs text-yellow-500 mt-1">Pending review</p>
            </div>
            <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Plan</p>
              <p className="text-xl font-bold text-[#c4922a] mt-1 capitalize">{data?.subscription?.plan || "None"}</p>
              <p className="text-xs text-green-500 mt-1 capitalize">{data?.subscription?.status || "—"}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Next appointment */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-sm font-semibold text-[#1a2744] uppercase tracking-wide mb-4">Next Appointment</h2>
              {data?.next_appointment ? (
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-[#1a2744] rounded-lg flex items-center justify-center text-white text-xl">
                    📅
                  </div>
                  <div>
                    <p className="font-semibold text-[#1a2744] capitalize">
                      {data.next_appointment.type.replace(/_/g, " ")}
                    </p>
                    <p className="text-sm text-gray-500 mt-0.5">
                      {new Date(data.next_appointment.scheduled_at).toLocaleDateString([], {
                        weekday: "long", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                    <p className="text-xs text-gray-400 capitalize mt-0.5">via {data.next_appointment.meeting_type}</p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-gray-400 text-sm">No upcoming appointments</p>
                  <a href="/appointments" className="text-[#c4922a] text-sm mt-2 inline-block hover:underline">
                    Schedule one →
                  </a>
                </div>
              )}
            </div>

            {/* Recent Activity */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-sm font-semibold text-[#1a2744] uppercase tracking-wide mb-4">Recent Activity</h2>
              <div className="space-y-3">
                {data?.recent_activity?.slice(0, 5).map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3">
                    <div className="w-8 h-8 bg-[#0d7a6e] rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                      TS
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#1a2744] truncate">{activity.summary}</p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {new Date(activity.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        {" · "}{activity.channel.replace("_", " ")}
                      </p>
                    </div>
                  </div>
                ))}
                {(!data?.recent_activity || data.recent_activity.length === 0) && (
                  <p className="text-gray-400 text-sm text-center py-2">No recent activity</p>
                )}
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex gap-3 flex-wrap">
            <a
              href="/disputes"
              className="bg-[#c4922a] text-white px-5 py-3 rounded-lg font-medium hover:bg-[#d9a84e] transition-colors"
            >
              + Start New Dispute
            </a>
            <a
              href="/chat"
              className="bg-[#1a2744] text-white px-5 py-3 rounded-lg font-medium hover:bg-[#2a3a5e] transition-colors"
            >
              💬 Message Tim Shaw
            </a>
            <a
              href="/documents"
              className="bg-white text-[#1a2744] border border-gray-200 px-5 py-3 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              📁 View Documents
            </a>
          </div>
        </main>
      </div>
    </div>
  );
}
