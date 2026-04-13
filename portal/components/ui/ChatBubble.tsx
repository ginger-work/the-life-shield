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
        <div className="w-8 h-8 bg-[#0d7a6e] rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0 mt-1">
          TS
        </div>
      )}

      <div className={`max-w-[70%] ${isFromTimShaw ? "" : "items-end flex flex-col"}`}>
        {isFromTimShaw && (
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-[#0d7a6e]">{agent || "Tim Shaw"}</span>
            <span className="text-xs bg-[#0d7a6e] text-white px-1.5 py-0.5 rounded-full">AI Agent</span>
          </div>
        )}

        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isFromTimShaw
              ? "bg-[#1a2744] text-white rounded-tl-none"
              : "bg-[#c4922a] text-white rounded-tr-none"
          }`}
        >
          {message}
        </div>

        <div className="text-xs text-gray-400 mt-1">
          {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          {channel && channel !== "portal_chat" && (
            <span className="ml-1 capitalize text-gray-300">via {channel.replace("_", " ")}</span>
          )}
        </div>
      </div>
    </div>
  );
}
