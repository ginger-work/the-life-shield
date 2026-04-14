"use client";

interface ChatBubbleProps {
  message: string;
  direction: "inbound" | "outbound";
  agent?: string;
  timestamp: string;
  channel?: string;
}

export function ChatBubble({ message, direction, agent, timestamp, channel }: ChatBubbleProps) {
  const isFromTimShaw = direction === "outbound";

  return (
    <div className={`flex gap-3 ${isFromTimShaw ? "justify-start" : "justify-end"}`}>
      {isFromTimShaw && (
        <div className="w-8 h-8 bg-[#0d7a6e] rounded-full flex items-center justify-center text-white text-xs font-semibold flex-shrink-0 mt-1 tracking-wide">
          TS
        </div>
      )}

      <div className={`max-w-[70%] ${isFromTimShaw ? "" : "items-end flex flex-col"}`}>
        {isFromTimShaw && (
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs font-semibold text-[#0d7a6e]">{agent || "Tim Shaw"}</span>
            <span className="text-xs bg-[#0d7a6e]/10 text-[#0d7a6e] px-2 py-0.5 rounded-full font-medium border border-[#0d7a6e]/20">
              AI Agent
            </span>
          </div>
        )}

        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isFromTimShaw
              ? "bg-white text-[#111827] border border-gray-200 rounded-tl-sm shadow-sm"
              : "bg-[#1a2744] text-white rounded-tr-sm"
          }`}
        >
          {message}
        </div>

        <div className="text-xs text-gray-400 mt-1.5">
          {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          {channel && channel !== "portal_chat" && (
            <span className="ml-1.5 text-gray-300 capitalize">via {channel.replace("_", " ")}</span>
          )}
        </div>
      </div>
    </div>
  );
}
