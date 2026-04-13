"use client";

import { useState, useRef, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ChatBubble } from "@/components/ui/ChatBubble";
import { api, ChatMessage } from "@/lib/api";

const DISCLOSURE = "Tim Shaw is an AI agent. Human supervisors monitor all conversations. Never share your full SSN via chat.";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      direction: "outbound",
      content: "Hi! I'm Tim Shaw, your AI Client Success Agent at The Life Shield. I'm here to help with your credit journey 24/7. What can I help you with today?",
      channel: "portal_chat",
      created_at: new Date().toISOString(),
      agent: "Tim Shaw",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [channel, setChannel] = useState("portal_chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
      const response = await api.agents.chat(userMessage.content, channel);

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
          content: "🔔 A human specialist has been notified and will follow up shortly.",
          channel,
          created_at: new Date().toISOString(),
          agent: "System",
        };
        setMessages((prev) => [...prev, escalationNote]);
      }
    } catch (err) {
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

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Tim Shaw" />

        {/* AI Disclosure Banner */}
        <div className="bg-[#0d7a6e]/10 border-b border-[#0d7a6e]/20 px-6 py-2">
          <p className="text-xs text-[#0d7a6e] text-center">{DISCLOSURE}</p>
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
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
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
    </div>
  );
}
