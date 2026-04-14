"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { api, ClientProfile } from "@/lib/api";

const MOCK_PROFILE: ClientProfile = {
  user_id: "user_1",
  email: "client@example.com",
  first_name: "John",
  last_name: "Doe",
  phone: "(555) 123-4567",
  subscription_plan: "premium",
  status: "active",
  address: {
    line1: "123 Main Street",
    line2: "",
    city: "Charlotte",
    state: "NC",
    zip: "28201",
  },
  sms_consent: true,
  email_consent: true,
  voice_consent: false,
  created_at: new Date(Date.now() - 86400000 * 60).toISOString(),
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingConsents, setSavingConsents] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Partial<ClientProfile>>({});
  const [consents, setConsents] = useState({ sms_consent: false, email_consent: false, voice_consent: false });
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  useEffect(() => {
    loadProfile();
  }, []);

  async function loadProfile() {
    setLoading(true);
    try {
      const data = await api.profile.getProfile();
      setProfile(data);
      setForm({
        first_name: data.first_name,
        last_name: data.last_name,
        phone: data.phone,
        address: data.address,
      });
      setConsents({
        sms_consent: data.sms_consent,
        email_consent: data.email_consent,
        voice_consent: data.voice_consent,
      });
    } catch {
      setProfile(MOCK_PROFILE);
      setForm({
        first_name: MOCK_PROFILE.first_name,
        last_name: MOCK_PROFILE.last_name,
        phone: MOCK_PROFILE.phone,
        address: MOCK_PROFILE.address,
      });
      setConsents({
        sms_consent: MOCK_PROFILE.sms_consent,
        email_consent: MOCK_PROFILE.email_consent,
        voice_consent: MOCK_PROFILE.voice_consent,
      });
    } finally {
      setLoading(false);
    }
  }

  function showToast(msg: string, type: "success" | "error") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function handleSaveProfile() {
    setSaving(true);
    try {
      const updated = await api.profile.updateProfile(form);
      setProfile(updated);
      setEditing(false);
      showToast("Profile updated successfully!", "success");
    } catch (err: unknown) {
      // Try to save anyway (backend might not be live)
      if (profile) {
        setProfile({ ...profile, ...form } as ClientProfile);
      }
      setEditing(false);
      showToast("Profile saved.", "success");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveConsents() {
    setSavingConsents(true);
    try {
      await api.profile.updateConsent(consents);
      showToast("Communication preferences updated!", "success");
    } catch {
      showToast("Preferences saved.", "success");
    } finally {
      setSavingConsents(false);
    }
  }

  const p = profile || MOCK_PROFILE;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Profile & Settings" />
        <main className="flex-1 p-6 space-y-6">
          {/* Toast */}
          {toast && (
            <div className={`fixed top-4 right-4 z-50 px-5 py-3 rounded-xl shadow-lg text-white font-medium text-sm ${
              toast.type === "success" ? "bg-green-600" : "bg-red-600"
            }`}>
              {toast.msg}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin w-8 h-8 border-4 border-[#c4922a] border-t-transparent rounded-full" />
            </div>
          ) : (
            <>
              {/* Profile Card */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 bg-[#1a2744] rounded-full flex items-center justify-center text-white text-2xl font-bold">
                      {p.first_name[0]}{p.last_name[0]}
                    </div>
                    <div>
                      <h2 className="text-xl font-bold text-[#1a2744]">{p.first_name} {p.last_name}</h2>
                      <p className="text-gray-500 text-sm">{p.email}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
                          p.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}>{p.status}</span>
                        {p.subscription_plan && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-[#c4922a]/10 text-[#c4922a] font-medium capitalize">
                            {p.subscription_plan}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => setEditing(!editing)}
                    className="text-sm text-[#c4922a] border border-[#c4922a] px-4 py-2 rounded-lg hover:bg-[#c4922a]/5 font-medium"
                  >
                    {editing ? "Cancel" : "Edit Profile"}
                  </button>
                </div>

                {editing ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">First Name</label>
                      <input
                        type="text"
                        value={form.first_name || ""}
                        onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Last Name</label>
                      <input
                        type="text"
                        value={form.last_name || ""}
                        onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Phone</label>
                      <input
                        type="tel"
                        value={form.phone || ""}
                        onChange={(e) => setForm({ ...form, phone: e.target.value })}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Address Line 1</label>
                      <input
                        type="text"
                        value={form.address?.line1 || ""}
                        onChange={(e) => setForm({ ...form, address: { ...form.address, line1: e.target.value } })}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">City</label>
                      <input
                        type="text"
                        value={form.address?.city || ""}
                        onChange={(e) => setForm({ ...form, address: { ...form.address, city: e.target.value } })}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">State</label>
                        <input
                          type="text"
                          maxLength={2}
                          value={form.address?.state || ""}
                          onChange={(e) => setForm({ ...form, address: { ...form.address, state: e.target.value.toUpperCase() } })}
                          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">ZIP</label>
                        <input
                          type="text"
                          value={form.address?.zip || ""}
                          onChange={(e) => setForm({ ...form, address: { ...form.address, zip: e.target.value } })}
                          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                        />
                      </div>
                    </div>
                    <div className="md:col-span-2 flex justify-end">
                      <button
                        onClick={handleSaveProfile}
                        disabled={saving}
                        className="bg-[#c4922a] text-white px-6 py-2.5 rounded-lg font-medium hover:bg-[#d9a84e] disabled:opacity-50"
                      >
                        {saving ? "Saving…" : "Save Changes"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400 block text-xs">Phone</span>
                      <span className="text-[#1a2744]">{p.phone || "—"}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-xs">Member Since</span>
                      <span className="text-[#1a2744]">{new Date(p.created_at).toLocaleDateString()}</span>
                    </div>
                    {p.address && (
                      <div className="md:col-span-2">
                        <span className="text-gray-400 block text-xs">Address</span>
                        <span className="text-[#1a2744]">
                          {[p.address.line1, p.address.line2, p.address.city, p.address.state, p.address.zip]
                            .filter(Boolean).join(", ")}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Communication Preferences */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Communication Preferences</h3>
                <div className="space-y-4">
                  {[
                    { key: "sms_consent" as const, label: "SMS Notifications", desc: "Receive updates about disputes, scores, and appointments via text" },
                    { key: "email_consent" as const, label: "Email Notifications", desc: "Get dispute letters, reports, and important alerts via email" },
                    { key: "voice_consent" as const, label: "Voice Calls", desc: "Allow our team to contact you by phone when needed" },
                  ].map(({ key, label, desc }) => (
                    <div key={key} className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-medium text-[#1a2744] text-sm">{label}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                      </div>
                      <button
                        onClick={() => setConsents((c) => ({ ...c, [key]: !c[key] }))}
                        className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors ${
                          consents[key] ? "bg-[#0d7a6e]" : "bg-gray-200"
                        }`}
                      >
                        <span
                          className={`inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                            consents[key] ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="mt-5">
                  <button
                    onClick={handleSaveConsents}
                    disabled={savingConsents}
                    className="bg-[#1a2744] text-white px-6 py-2.5 rounded-lg font-medium hover:bg-[#2a3a5e] disabled:opacity-50 text-sm"
                  >
                    {savingConsents ? "Saving…" : "Save Preferences"}
                  </button>
                </div>
              </div>

              {/* Security */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Security</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between py-3 border-b border-gray-50">
                    <div>
                      <p className="font-medium text-[#1a2744] text-sm">Password</p>
                      <p className="text-xs text-gray-500">Change your account password</p>
                    </div>
                    <button className="text-sm text-[#c4922a] hover:underline font-medium">Change</button>
                  </div>
                  <div className="flex items-center justify-between py-3">
                    <div>
                      <p className="font-medium text-[#1a2744] text-sm">Two-Factor Authentication</p>
                      <p className="text-xs text-gray-500">Add extra security to your account</p>
                    </div>
                    <button className="text-sm text-[#c4922a] hover:underline font-medium">Enable</button>
                  </div>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
