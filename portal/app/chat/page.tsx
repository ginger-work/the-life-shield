"use client";

import { useState, useRef, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ChatBubble } from "@/components/ui/ChatBubble";
import { CallModal } from "@/components/ui/CallModal";
import { VideoCallModal } from "@/components/ui/VideoCallModal";
import { api, ChatMessage, CallRecord } from "@/lib/api";

const DISCLOSURE = "Tim Shaw is an AI agent. Human supervisors monitor all conversations. Never share your full SSN via chat.";

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  direction: "outbound",
  content: "Hi! I'm Tim Shaw, your AI Client Success Agent at The Life Shield. I'm here to help with your credit journey 24/7. What can I help you with today?",
  channel: "portal_chat",
  created_at: new Date().toISOString(),
  agent: "Tim Shaw",
};

function formatCallDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [channel, setChannel] = useState("portal_chat");
  const [agentStatus, setAgentStatus] = useState<string>("online");
  const [showEscalate, setShowEscalate] = useState(false);
  const [escalateReason, setEscalateReason] = useState("");

  // Call/Video state
  const [showCallModal, setShowCallModal] = useState(false);
  const [showVideoModal, setShowVideoModal] = useState(false);
  const [callHistory, setCallHistory] = useState<CallRecord[]>([]);
  const [showScheduleCallback, setShowScheduleCallback] = useState(false);
  const [callbackTime, setCallbackTime] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadInitialData() {
    setLoadingHistory(true);
    try {
      const userId = typeof window !== "undefined" ? localStorage.getItem("user_id") || "me" : "me";

      const [statusRes, historyRes] = await Promise.allSettled([
        api.timShaw.getAgentStatus(),
        api.timShaw.getChatHistory(userId, 30),
      ]);

      if (statusRes.status === "fulfilled") {
        setAgentStatus(statusRes.value.status || "online");
      }

      if (historyRes.status === "fulfilled" && historyRes.value.messages?.length > 0) {
        setMessages([WELCOME_MESSAGE, ...historyRes.value.messages]);
      }
    } catch {
      // Keep welcome message
    } finally {
      setLoadingHistory(false);
    }

    // Load call history from localStorage (MVP)
    try {
      const stored = localStorage.getItem("call_history");
      if (stored) setCallHistory(JSON.parse(stored));
    } catch { /* ignore */ }
  }

  function handleCallLogged(entry: { type: string; duration: number; timestamp: string }) {
    const record: CallRecord = {
      id: `${entry.type}_${Date.now()}`,
      type: entry.type as "voice" | "video",
      duration: entry.duration,
      status: "completed",
      timestamp: entry.timestamp,
    };

    const updated = [record, ...callHistory].slice(0, 10); // keep last 10
    setCallHistory(updated);
    localStorage.setItem("call_history", JSON.stringify(updated));

    // Add a system message to chat
    const callNote: ChatMessage = {
      id: `callnote_${Date.now()}`,
      direction: "outbound",
      content: `${entry.type === "video" ? "Video call" : "Voice call"} with Tim Shaw — ${formatCallDuration(entry.duration)}`,
      channel,
      created_at: entry.timestamp,
      agent: "System",
    };
    setMessages((prev) => [...prev, callNote]);
  }

  async function sendMessage() {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      direction: "inbound",
      content: input.trim(),
      channel,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await api.timShaw.sendMessage(userMessage.content, channel);

      const agentMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        direction: "outbound",
        content: response.response,
        channel: response.channel,
        created_at: response.timestamp,
        agent: response.agent,
      };

      setMessages((prev) => [...prev, agentMessage]);

      if (response.requires_human) {
        const escalationNote: ChatMessage = {
          id: (Date.now() + 2).toString(),
          direction: "outbound",
          content: "A licensed specialist has been notified and will follow up with you shortly.",
          channel,
          created_at: new Date().toISOString(),
          agent: "System",
        };
        setMessages((prev) => [...prev, escalationNote]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          direction: "outbound",
          content: "I'm having a technical issue. Please try again in a moment or contact us at support@thelifeshield.com",
          channel,
          created_at: new Date().toISOString(),
          agent: "Tim Shaw",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleEscalate() {
    try {
      await api.timShaw.escalateToHuman(escalateReason, "User requested human assistance");
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          direction: "outbound",
          content: "Your request has been escalated. A licensed specialist from our team will reach out to you shortly.",
          channel,
          created_at: new Date().toISOString(),
          agent: "System",
        },
      ]);
      setShowEscalate(false);
      setEscalateReason("");
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          direction: "outbound",
          content: "Your request has been submitted. A team member will contact you within 24 hours.",
          channel,
          created_at: new Date().toISOString(),
          agent: "System",
        },
      ]);
      setShowEscalate(false);
    }
  }

  function handleScheduleCallback() {
    if (!callbackTime) return;
    const note: ChatMessage = {
      id: Date.now().toString(),
      direction: "outbound",
      content: `Callback scheduled for ${new Date(callbackTime).toLocaleString()}. Tim Shaw will reach out at that time.`,
      channel,
      created_at: new Date().toISOString(),
      agent: "System",
    };
    setMessages((prev) => [...prev, note]);
    setShowScheduleCallback(false);
    setCallbackTime("");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Tim Shaw" />

        {/* AI Disclosure Banner */}
        <div className="bg-[#0d7a6e]/10 border-b border-[#0d7a6e]/20 px-6 py-2 flex items-center justify-between">
          <p className="text-xs text-[#0d7a6e]">{DISCLOSURE}</p>
          <button
            onClick={() => setShowEscalate(true)}
            className="text-xs text-gray-500 hover:text-[#1a2744] underline ml-4 whitespace-nowrap"
          >
            Request Human
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Main chat area */}
          <div className="flex-1 flex flex-col overflow-hidden">

            {/* Channel tabs + Call buttons */}
            <div className="bg-white border-b border-gray-200 px-6 flex items-center gap-4">
              {["portal_chat", "sms", "email"].map((ch) => (
                <button
                  key={ch}
                  onClick={() => setChannel(ch)}
                  className={`py-3 text-sm font-medium border-b-2 capitalize transition-colors ${
                    channel === ch
                      ? "border-[#c4922a] text-[#c4922a]"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {ch.replace("_", " ")}
                </button>
              ))}

              {/* Status indicator */}
              <div className="flex items-center gap-2 py-3">
                <div className={`w-2 h-2 rounded-full ${agentStatus === "online" ? "bg-green-400" : "bg-gray-300"}`} />
                <span className="text-xs text-gray-500 capitalize">{agentStatus}</span>
              </div>

              {/* ── Call & Video buttons ── */}
              <div className="ml-auto flex items-center gap-2 py-2">
                <button
                  onClick={() => setShowCallModal(true)}
                  className="flex items-center gap-2 bg-[#0d7a6e] hover:bg-[#0b6a5e] text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                  title="Call Tim Shaw"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
                  </svg>
                  Call Tim
                </button>

                <button
                  onClick={() => setShowVideoModal(true)}
                  className="flex items-center gap-2 bg-[#1a2744] hover:bg-[#2a3a5e] text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                  title="Video Call with Tim Shaw"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                  </svg>
                  Video Call
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {loadingHistory && (
                <div className="text-center py-4">
                  <div className="animate-spin w-5 h-5 border-2 border-[#c4922a] border-t-transparent rounded-full mx-auto" />
                  <p className="text-xs text-gray-400 mt-2">Loading history…</p>
                </div>
              )}

              {messages.map((msg) => (
                <ChatBubble
                  key={msg.id}
                  message={msg.content}
                  direction={msg.direction}
                  agent={msg.agent}
                  timestamp={msg.created_at}
                  channel={msg.channel}
                />
              ))}

              {loading && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 bg-[#0d7a6e] rounded-full flex items-center justify-center text-white text-xs font-bold">TS</div>
                  <div className="bg-[#1a2744] px-4 py-3 rounded-2xl rounded-tl-none">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="bg-white border-t border-gray-200 p-4">
              <div className="flex gap-3 max-w-4xl mx-auto">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder="Message Tim Shaw..."
                  rows={1}
                  className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] focus:border-transparent"
                />
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || loading}
                  className="bg-[#c4922a] text-white px-5 py-3 rounded-xl font-medium hover:bg-[#d9a84e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Send
                </button>
              </div>
              <p className="text-xs text-gray-400 text-center mt-2">
                Press Enter to send · Shift+Enter for new line
              </p>
            </div>
          </div>

          {/* ── Right Sidebar: Tim's Status + Call History ── */}
          <div className="w-72 border-l border-gray-100 bg-gray-50 flex flex-col overflow-y-auto hidden lg:flex">

            {/* Agent Profile Card */}
            <div className="p-5 border-b border-gray-100">
              <div className="flex items-center gap-3 mb-3">
                <div className="relative">
                  <div className="w-12 h-12 rounded-full bg-[#0d7a6e] flex items-center justify-center text-white font-bold">
                    TS
                  </div>
                  <div className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white ${
                    agentStatus === "online" ? "bg-green-400" : "bg-gray-300"
                  }`} />
                </div>
                <div>
                  <p className="font-semibold text-[#1a2744] text-sm">Tim Shaw</p>
                  <p className="text-xs text-gray-500">AI Client Success Agent</p>
                </div>
              </div>

              {/* Availability badge */}
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                agentStatus === "online"
                  ? "bg-green-50 text-green-700 border border-green-100"
                  : "bg-gray-100 text-gray-600 border border-gray-200"
              }`}>
                <div className={`w-2 h-2 rounded-full ${agentStatus === "online" ? "bg-green-500" : "bg-gray-400"}`} />
                {agentStatus === "online" ? "Available for calls" : "Busy"}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="p-4 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Quick Actions</p>
              <div className="space-y-2">
                <button
                  onClick={() => setShowCallModal(true)}
                  className="w-full flex items-center gap-3 bg-white hover:bg-[#0d7a6e]/5 border border-gray-200 text-[#1a2744] text-sm font-medium px-3 py-2.5 rounded-xl transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-[#0d7a6e]/10 flex items-center justify-center">
                    <svg className="w-4 h-4 text-[#0d7a6e]" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
                    </svg>
                  </div>
                  Call Tim Shaw
                </button>

                <button
                  onClick={() => setShowVideoModal(true)}
                  className="w-full flex items-center gap-3 bg-white hover:bg-[#1a2744]/5 border border-gray-200 text-[#1a2744] text-sm font-medium px-3 py-2.5 rounded-xl transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-[#1a2744]/10 flex items-center justify-center">
                    <svg className="w-4 h-4 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                    </svg>
                  </div>
                  Video Call
                </button>

                <button
                  onClick={() => setShowScheduleCallback(true)}
                  className="w-full flex items-center gap-3 bg-white hover:bg-[#c4922a]/5 border border-gray-200 text-[#1a2744] text-sm font-medium px-3 py-2.5 rounded-xl transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-[#c4922a]/10 flex items-center justify-center">
                    <svg className="w-4 h-4 text-[#c4922a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  Schedule Callback
                </button>
              </div>
            </div>

            {/* Recent Call History */}
            <div className="p-4 flex-1">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Recent Calls</p>

              {callHistory.length === 0 ? (
                <div className="text-center py-8">
                  <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                    <svg className="w-6 h-6 text-gray-300" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
                    </svg>
                  </div>
                  <p className="text-xs text-gray-400">No calls yet</p>
                  <p className="text-xs text-gray-300 mt-1">Your call history will appear here</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {callHistory.map((call) => (
                    <div key={call.id} className="bg-white border border-gray-100 rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
                          call.type === "video" ? "bg-[#1a2744]/10" : "bg-[#0d7a6e]/10"
                        }`}>
                          {call.type === "video" ? (
                            <svg className="w-3 h-3 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                            </svg>
                          ) : (
                            <svg className="w-3 h-3 text-[#0d7a6e]" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
                            </svg>
                          )}
                        </div>
                        <span className="text-xs font-medium text-[#1a2744] capitalize">{call.type} call</span>
                        <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-full ${
                          call.status === "completed" ? "bg-green-50 text-green-600" : "bg-red-50 text-red-500"
                        }`}>
                          {call.status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-xs text-gray-400 ml-8">
                        <span>{formatCallDuration(call.duration)}</span>
                        <span>{new Date(call.timestamp).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Call Modal ── */}
      {showCallModal && (
        <CallModal
          onClose={() => setShowCallModal(false)}
          onSwitchToVideo={() => setShowVideoModal(true)}
          onCallLogged={handleCallLogged}
        />
      )}

      {/* ── Video Call Modal ── */}
      {showVideoModal && (
        <VideoCallModal
          onClose={() => setShowVideoModal(false)}
          onSwitchToAudio={() => setShowCallModal(true)}
          onCallLogged={handleCallLogged}
        />
      )}

      {/* ── Schedule Callback Modal ── */}
      {showScheduleCallback && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold text-[#1a2744] mb-1">Schedule a Callback</h3>
            <p className="text-gray-500 text-sm mb-4">Tim Shaw will call you at your preferred time.</p>

            <label className="block text-sm font-medium text-gray-700 mb-1">Preferred Date & Time</label>
            <input
              type="datetime-local"
              value={callbackTime}
              onChange={(e) => setCallbackTime(e.target.value)}
              min={new Date().toISOString().slice(0, 16)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
            />

            <div className="flex gap-3">
              <button
                onClick={() => setShowScheduleCallback(false)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleScheduleCallback}
                disabled={!callbackTime}
                className="flex-1 bg-[#c4922a] text-white py-2.5 rounded-lg font-medium hover:bg-[#d9a84e] disabled:opacity-50"
              >
                Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Escalate to Human Modal ── */}
      {showEscalate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-lg font-bold text-[#1a2744] mb-1">Request Human Support</h3>
            <p className="text-gray-500 text-sm mb-4">A member of our team will follow up with you shortly.</p>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
            <select
              value={escalateReason}
              onChange={(e) => setEscalateReason(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
            >
              <option value="">Select a reason…</option>
              <option value="complex_dispute">Complex dispute question</option>
              <option value="account_issue">Account or billing issue</option>
              <option value="legal_question">Legal question</option>
              <option value="urgent">Urgent matter</option>
              <option value="other">Other</option>
            </select>
            <div className="flex gap-3">
              <button onClick={() => setShowEscalate(false)} className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium">
                Cancel
              </button>
              <button
                onClick={handleEscalate}
                disabled={!escalateReason}
                className="flex-1 bg-[#1a2744] text-white py-2.5 rounded-lg font-medium hover:bg-[#2a3a5e] disabled:opacity-50"
              >
                Submit Request
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
