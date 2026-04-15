"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";

interface VideoCallModalProps {
  onClose: () => void;
  onSwitchToAudio: () => void;
  onCallLogged: (entry: { type: string; duration: number; timestamp: string }) => void;
}

type CallStatus = "calling" | "connected" | "ended" | "failed";

export function VideoCallModal({ onClose, onSwitchToAudio, onCallLogged }: VideoCallModalProps) {
  const [status, setStatus] = useState<CallStatus>("calling");
  const [callId, setCallId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [muted, setMuted] = useState(false);
  const [videoOff, setVideoOff] = useState(false);
  const [cameraError, setCameraError] = useState(false);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  // Start camera + simulate connection
  useEffect(() => {
    let connectTimer: ReturnType<typeof setTimeout>;
    let ticker: ReturnType<typeof setInterval>;

    const init = async () => {
      // Try to get camera
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        streamRef.current = stream;
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = stream;
        }
      } catch {
        setCameraError(true);
      }

      // Initiate call
      try {
        const res = await api.calls.initiateVideoCall();
        setCallId(res.call_id);
      } catch {
        setCallId(`video_${Date.now()}`);
      }

      // Simulate connecting
      connectTimer = setTimeout(() => {
        setStatus("connected");
        ticker = setInterval(() => setElapsed((e) => e + 1), 1000);
      }, 2500);
    };

    init();

    return () => {
      clearTimeout(connectTimer);
      clearInterval(ticker);
      stopStream();
    };
  }, [stopStream]);

  // Toggle video tracks
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.getVideoTracks().forEach((t) => {
        t.enabled = !videoOff;
      });
    }
  }, [videoOff]);

  // Toggle audio tracks
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.getAudioTracks().forEach((t) => {
        t.enabled = !muted;
      });
    }
  }, [muted]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const endCall = useCallback(async () => {
    setStatus("ended");
    stopStream();
    if (callId) {
      try {
        await api.calls.endCall(callId);
      } catch { /* no-op */ }
    }
    onCallLogged({ type: "video", duration: elapsed, timestamp: new Date().toISOString() });
    setTimeout(onClose, 1500);
  }, [callId, elapsed, onClose, onCallLogged, stopStream]);

  const statusLabel: Record<CallStatus, string> = {
    calling: "Calling Tim Shaw…",
    connected: "Connected",
    ended: "Call Ended",
    failed: "Call Failed",
  };

  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4">
      <div className="bg-[#0f1a2e] rounded-3xl overflow-hidden max-w-2xl w-full shadow-2xl">

        {/* Video area */}
        <div className="relative bg-[#0a1020] aspect-video w-full">

          {/* Remote (Tim Shaw) video - placeholder */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            {status === "connected" ? (
              <>
                {/* Simulated remote feed */}
                <div className="w-32 h-32 rounded-full bg-[#0d7a6e] flex items-center justify-center text-white text-5xl font-bold mb-4">
                  TS
                </div>
                <p className="text-white/60 text-sm">Tim Shaw — Video feed</p>
                <p className="text-white/30 text-xs mt-1">(Twilio Video integration pending)</p>
              </>
            ) : status === "calling" ? (
              <>
                <div className="w-32 h-32 rounded-full bg-[#0d7a6e] animate-pulse flex items-center justify-center text-white text-5xl font-bold mb-4">
                  TS
                </div>
                <p className="text-white/80 text-lg font-medium">Calling Tim Shaw…</p>
                <div className="flex gap-1 mt-3">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="w-2 h-2 bg-white/50 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
              </>
            ) : (
              <p className="text-white/60 text-lg">Call Ended</p>
            )}
          </div>

          {/* Local video (PIP) */}
          <div className="absolute bottom-4 right-4 w-36 h-24 bg-[#1a2744] rounded-xl overflow-hidden border-2 border-white/20 shadow-lg">
            {!videoOff && !cameraError ? (
              <video
                ref={localVideoRef}
                autoPlay
                muted
                playsInline
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-[#1a2744]">
                <svg className="w-8 h-8 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3l18 18" />
                </svg>
              </div>
            )}
            <div className="absolute bottom-1 left-1">
              <span className="text-white/60 text-xs">You</span>
            </div>
          </div>

          {/* Status + timer overlay */}
          <div className="absolute top-4 left-4 flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                status === "calling" ? "bg-yellow-400 animate-pulse" :
                status === "connected" ? "bg-green-400" : "bg-gray-400"
              }`}
            />
            <span className="text-white/80 text-sm font-medium">{statusLabel[status]}</span>
            {status === "connected" && (
              <span className="text-white/60 text-sm font-mono">{formatTime(elapsed)}</span>
            )}
          </div>

          {cameraError && (
            <div className="absolute top-4 right-4 bg-yellow-500/20 border border-yellow-500/40 rounded-lg px-3 py-1">
              <p className="text-yellow-400 text-xs">Camera unavailable</p>
            </div>
          )}
        </div>

        {/* Controls bar */}
        <div className="bg-[#0f1a2e] px-6 py-5 flex items-center justify-between">
          {/* Left: mute + video */}
          <div className="flex gap-3">
            <button
              onClick={() => setMuted((m) => !m)}
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-colors
                ${muted ? "bg-red-500 text-white" : "bg-white/10 text-white hover:bg-white/20"}`}
              title={muted ? "Unmute" : "Mute"}
            >
              {muted ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              )}
            </button>

            <button
              onClick={() => setVideoOff((v) => !v)}
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-colors
                ${videoOff ? "bg-red-500 text-white" : "bg-white/10 text-white hover:bg-white/20"}`}
              title={videoOff ? "Turn Video On" : "Turn Video Off"}
            >
              {videoOff ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3l18 18" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                </svg>
              )}
            </button>
          </div>

          {/* Center: end call */}
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

          {/* Right: switch to audio */}
          <button
            onClick={() => { endCall(); onSwitchToAudio(); }}
            className="bg-white/10 hover:bg-white/20 text-white text-xs px-4 py-2 rounded-full transition-colors"
          >
            Audio Only
          </button>
        </div>

        {status === "connected" && (
          <p className="text-center text-white/30 text-xs pb-3">
            Call is being recorded for quality assurance
          </p>
        )}
      </div>
    </div>
  );
}
