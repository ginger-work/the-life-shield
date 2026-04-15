"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

interface CallModalProps {
  onClose: () => void;
  onSwitchToVideo: () => void;
  onCallLogged: (entry: { type: string; duration: number; timestamp: string }) => void;
}

type CallStatus = "calling" | "connected" | "ended" | "failed";

export function CallModal({ onClose, onSwitchToVideo, onCallLogged }: CallModalProps) {
  const [status, setStatus] = useState<CallStatus>("calling");
  const [callId, setCallId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [muted, setMuted] = useState(false);

  // Simulate call connection after 2 seconds (MVP)
  useEffect(() => {
    let connectTimer: ReturnType<typeof setTimeout>;
    let ticker: ReturnType<typeof setInterval>;

    const initiateCall = async () => {
      try {
        const res = await api.calls.initiateCall();
        setCallId(res.call_id);
      } catch {
        // MVP: use a local ID
        setCallId(`call_${Date.now()}`);
      }

      connectTimer = setTimeout(() => {
        setStatus("connected");
        ticker = setInterval(() => setElapsed((e) => e + 1), 1000);
      }, 2000);
    };

    initiateCall();

    return () => {
      clearTimeout(connectTimer);
      clearInterval(ticker);
    };
  }, []);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const endCall = useCallback(async () => {
    setStatus("ended");
    if (callId) {
      try {
        await api.calls.endCall(callId);
      } catch { /* no-op */ }
    }
    onCallLogged({ type: "voice", duration: elapsed, timestamp: new Date().toISOString() });
    setTimeout(onClose, 1500);
  }, [callId, elapsed, onClose, onCallLogged]);

  const statusLabel: Record<CallStatus, string> = {
    calling: "Calling Tim Shaw…",
    connected: "Connected",
    ended: "Call Ended",
    failed: "Call Failed",
  };

  const statusColor: Record<CallStatus, string> = {
    calling: "text-yellow-400",
    connected: "text-green-400",
    ended: "text-gray-400",
    failed: "text-red-400",
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a2744] rounded-3xl p-8 max-w-sm w-full shadow-2xl text-center">
        {/* Avatar */}
        <div className="relative inline-block mb-6">
          <div
            className={`w-24 h-24 rounded-full bg-[#0d7a6e] flex items-center justify-center text-white text-3xl font-bold mx-auto
              ${status === "calling" ? "animate-pulse" : ""}`}
          >
            TS
          </div>
          {status === "connected" && (
            <div className="absolute inset-0 rounded-full border-4 border-green-400 animate-ping opacity-30" />
          )}
        </div>

        {/* Name */}
        <h2 className="text-white text-xl font-bold mb-1">Tim Shaw</h2>
        <p className="text-gray-400 text-sm mb-4">AI Client Success Agent</p>

        {/* Status */}
        <div className="flex items-center justify-center gap-2 mb-2">
          <div
            className={`w-2 h-2 rounded-full ${
              status === "calling" ? "bg-yellow-400 animate-pulse" :
              status === "connected" ? "bg-green-400" : "bg-gray-400"
            }`}
          />
          <span className={`text-sm font-medium ${statusColor[status]}`}>
            {statusLabel[status]}
          </span>
        </div>

        {/* Timer */}
        {status === "connected" && (
          <p className="text-white text-2xl font-mono mb-6">{formatTime(elapsed)}</p>
        )}
        {status !== "connected" && <div className="h-10 mb-2" />}

        {/* Controls */}
        <div className="flex items-center justify-center gap-6 mb-6">
          {/* Mute */}
          <button
            onClick={() => setMuted((m) => !m)}
            disabled={status !== "connected"}
            className={`w-14 h-14 rounded-full flex items-center justify-center transition-colors
              ${muted ? "bg-red-500 text-white" : "bg-white/10 text-white hover:bg-white/20"}
              disabled:opacity-30 disabled:cursor-not-allowed`}
            title={muted ? "Unmute" : "Mute"}
          >
            {muted ? (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            )}
          </button>

          {/* End Call */}
          <button
            onClick={endCall}
            disabled={status === "ended"}
            className="w-16 h-16 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center text-white transition-colors disabled:opacity-50"
            title="End Call"
          >
            <svg className="w-7 h-7" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
            </svg>
          </button>

          {/* Switch to Video */}
          <button
            onClick={() => { endCall(); onSwitchToVideo(); }}
            disabled={status !== "connected"}
            className="w-14 h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Switch to Video"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
          </button>
        </div>

        <p className="text-gray-500 text-xs">
          {status === "calling" ? "Connecting you to Tim Shaw…" :
           status === "connected" ? "Call is being recorded for quality assurance" :
           "Call ended"}
        </p>
      </div>
    </div>
  );
}
