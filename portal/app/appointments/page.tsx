"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { api, Appointment } from "@/lib/api";

const SESSION_TYPES = [
  { value: "credit_coaching", label: "Credit Coaching", duration: "45 min", description: "1-on-1 coaching on your credit strategy and next steps" },
  { value: "dispute_review", label: "Dispute Review", duration: "30 min", description: "Review active disputes and investigation outcomes" },
  { value: "strategy_call", label: "Full Strategy Call", duration: "60 min", description: "Comprehensive credit repair strategy session" },
];

const MOCK_APPOINTMENTS: Appointment[] = [
  {
    id: "a1",
    type: "credit_coaching",
    scheduled_at: new Date(Date.now() + 86400000 * 2).toISOString(),
    meeting_type: "video",
    status: "scheduled",
  },
  {
    id: "a2",
    type: "dispute_review",
    scheduled_at: new Date(Date.now() - 86400000 * 7).toISOString(),
    meeting_type: "phone",
    status: "completed",
    notes: "Reviewed Equifax dispute status. 15 days remaining.",
  },
];

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>(MOCK_APPOINTMENTS);
  const [showBooking, setShowBooking] = useState(false);
  const [selectedType, setSelectedType] = useState(SESSION_TYPES[0].value);
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedTime, setSelectedTime] = useState("");
  const [loading, setLoading] = useState(false);

  const upcoming = appointments.filter((a) => new Date(a.scheduled_at) > new Date() && a.status !== "cancelled");
  const past = appointments.filter((a) => new Date(a.scheduled_at) <= new Date() || a.status === "cancelled");

  async function bookAppointment() {
    if (!selectedDate || !selectedTime) return;
    setLoading(true);
    try {
      const scheduled_at = new Date(`${selectedDate}T${selectedTime}:00`).toISOString();
      await api.clients.bookAppointment({
        session_type: selectedType,
        scheduled_at,
        meeting_type: "video",
      });
      setAppointments((prev) => [
        ...prev,
        { id: Date.now().toString(), type: selectedType, scheduled_at, meeting_type: "video", status: "scheduled" },
      ]);
      setShowBooking(false);
      alert("Appointment booked! You'll receive a confirmation shortly.");
    } catch (e) {
      alert("Booking failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Appointments" />
        <main className="flex-1 p-6 space-y-6">
          <div className="flex justify-end">
            <button
              onClick={() => setShowBooking(true)}
              className="bg-[#c4922a] text-white px-5 py-2.5 rounded-lg font-medium hover:bg-[#d9a84e]"
            >
              + Schedule Session
            </button>
          </div>

          {/* Upcoming */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Upcoming</h2>
            {upcoming.length === 0 && (
              <div className="bg-white rounded-xl p-8 text-center border border-gray-100 shadow-sm">
                <p className="text-3xl mb-2">📅</p>
                <p className="text-gray-500">No upcoming appointments</p>
                <button onClick={() => setShowBooking(true)} className="text-[#c4922a] text-sm mt-2 hover:underline">
                  Book one now →
                </button>
              </div>
            )}
            {upcoming.map((apt) => {
              const session = SESSION_TYPES.find((s) => s.value === apt.type);
              return (
                <div key={apt.id} className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm flex items-center justify-between mb-3">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 bg-[#1a2744] rounded-xl flex items-center justify-center text-2xl">📅</div>
                    <div>
                      <p className="font-semibold text-[#1a2744]">{session?.label || apt.type}</p>
                      <p className="text-sm text-gray-500 mt-0.5">
                        {new Date(apt.scheduled_at).toLocaleDateString([], {
                          weekday: "long", month: "long", day: "numeric",
                        })} at {new Date(apt.scheduled_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5 capitalize">via {apt.meeting_type} · {session?.duration}</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="bg-[#0d7a6e] text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-[#13a396]">
                      Join
                    </button>
                    <button
                      className="border border-red-200 text-red-500 px-3 py-1.5 rounded-lg text-sm hover:bg-red-50"
                      onClick={() => setAppointments((prev) => prev.map((a) => a.id === apt.id ? { ...a, status: "cancelled" } : a))}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              );
            })}
          </section>

          {/* Past */}
          {past.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Past Sessions</h2>
              {past.map((apt) => {
                const session = SESSION_TYPES.find((s) => s.value === apt.type);
                return (
                  <div key={apt.id} className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm opacity-75 mb-3">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center text-xl">📋</div>
                      <div>
                        <p className="font-medium text-gray-600">{session?.label || apt.type}</p>
                        <p className="text-sm text-gray-400 mt-0.5">
                          {new Date(apt.scheduled_at).toLocaleDateString()}
                          {apt.status === "cancelled" && " · Cancelled"}
                          {apt.status === "completed" && " · Completed"}
                        </p>
                        {apt.notes && <p className="text-xs text-gray-500 mt-1 italic">{apt.notes}</p>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </section>
          )}

          {/* Booking Modal */}
          {showBooking && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
              <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl">
                <h2 className="text-lg font-bold text-[#1a2744] mb-4">Schedule a Session</h2>

                <label className="block text-sm font-medium text-gray-700 mb-2">Session Type</label>
                <div className="space-y-2 mb-4">
                  {SESSION_TYPES.map((s) => (
                    <label key={s.value} className={`block p-3 rounded-lg border-2 cursor-pointer transition-colors ${
                      selectedType === s.value ? "border-[#c4922a] bg-[#c4922a]/5" : "border-gray-200 hover:border-gray-300"
                    }`}>
                      <input
                        type="radio"
                        name="session_type"
                        value={s.value}
                        checked={selectedType === s.value}
                        onChange={() => setSelectedType(s.value)}
                        className="hidden"
                      />
                      <div className="font-medium text-[#1a2744]">{s.label} <span className="text-gray-400 font-normal text-sm">({s.duration})</span></div>
                      <div className="text-xs text-gray-500 mt-0.5">{s.description}</div>
                    </label>
                  ))}
                </div>

                <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
                <input
                  type="date"
                  value={selectedDate}
                  min={new Date().toISOString().split("T")[0]}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                />

                <label className="block text-sm font-medium text-gray-700 mb-1">Time (EST)</label>
                <select
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                >
                  <option value="">Select time</option>
                  {["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>

                <div className="flex gap-3">
                  <button
                    onClick={() => setShowBooking(false)}
                    className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={bookAppointment}
                    disabled={!selectedDate || !selectedTime || loading}
                    className="flex-1 bg-[#c4922a] text-white py-2.5 rounded-lg font-medium hover:bg-[#d9a84e] disabled:opacity-50"
                  >
                    {loading ? "Booking..." : "Book Session"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
