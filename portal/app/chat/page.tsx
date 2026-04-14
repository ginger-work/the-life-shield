"use client";

import { useState, useRef, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ChatBubble } from "@/components/ui/ChatBubble";
import { api, ChatMessage } from "@/lib/api";

const DISCLOSURE = "Tim Shaw is an AI agent. Human supervisors monitor all conversations. Never share your full SSN via chat.";

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  direction: "outbound",
  content: "Hi! I'm Tim Shaw, your AI Client Success Agent at The Life Shield. I'm here to help with your credit journey 24/7. What can I help you with today?",
  channel: "portal_chat",
  created_at: new Date().toISOString(),
  agent: "Tim Shaw",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [channel, setChannel] = useState("portal_chat");
  const [agentStatus, setAgentStatus] = useState<string>("online");
  const [showEscalate, setShowEscalate] = useState(false);
  const [escalateReason, setEscalateReason] = useState("");
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

        {/* Channel tabs */}
        <div className="bg-white border-b border-gray-200 px-6 flex gap-4">
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
          <div className="ml-auto flex items-center gap-2 py-3">
            <div className={`w-2 h-2 rounded-full ${agentStatus === "online" ? "bg-green-400" : "bg-gray-300"}`} />
            <span className="text-xs text-gray-500 capitalize">{agentStatus}</span>
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

      {/* Escalate to Human Modal */}
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
