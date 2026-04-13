"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, saveTokens } from "@/lib/api";

export default function RegisterPage() {
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    confirm: "",
    sms_consent: false,
    email_consent: true,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  function update(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (form.password !== form.confirm) {
      setError("Passwords do not match");
      return;
    }
    if (form.password.length < 12) {
      setError("Password must be at least 12 characters");
      return;
    }
    if (!form.email_consent) {
      setError("Email consent is required to receive your account information");
      return;
    }

    setLoading(true);
    try {
      const response = await api.auth.register({
        email: form.email,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
        sms_consent: form.sms_consent,
        email_consent: form.email_consent,
      });
      saveTokens(response);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#f8f9fb] flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-6">
          <div className="w-14 h-14 bg-[#1a2744] rounded-2xl flex items-center justify-center text-2xl mx-auto mb-3">🛡️</div>
          <h1 className="text-2xl font-bold text-[#1a2744]">Create Your Account</h1>
          <p className="text-gray-500 text-sm mt-1">Start rebuilding your credit with The Life Shield</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                <input
                  type="text"
                  value={form.first_name}
                  onChange={(e) => update("first_name", e.target.value)}
                  required
                  placeholder="John"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                <input
                  type="text"
                  value={form.last_name}
                  onChange={(e) => update("last_name", e.target.value)}
                  required
                  placeholder="Smith"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                required
                placeholder="john@example.com"
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                required
                placeholder="Min 12 characters"
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
              <input
                type="password"
                value={form.confirm}
                onChange={(e) => update("confirm", e.target.value)}
                required
                placeholder="Repeat password"
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a]"
              />
            </div>

            {/* Consent section */}
            <div className="bg-gray-50 rounded-xl p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Communication Consent</p>
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.email_consent}
                  onChange={(e) => update("email_consent", e.target.checked)}
                  className="mt-0.5 accent-[#c4922a]"
                />
                <span className="text-sm text-gray-600">
                  <strong>Email consent</strong> — I agree to receive account updates, dispute notifications, and program info via email. (Required)
                </span>
              </label>
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.sms_consent}
                  onChange={(e) => update("sms_consent", e.target.checked)}
                  className="mt-0.5 accent-[#c4922a]"
                />
                <span className="text-sm text-gray-600">
                  <strong>SMS consent</strong> — I agree to receive text messages from Tim Shaw AI for dispute updates and reminders. Standard rates apply.
                </span>
              </label>
            </div>

            <p className="text-xs text-gray-400">
              By creating an account, you agree to our Terms of Service and Privacy Policy. 
              Tim Shaw is an AI agent backed by human supervisors.
            </p>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#c4922a] text-white py-3 rounded-lg font-semibold hover:bg-[#d9a84e] disabled:opacity-50 transition-colors"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-4">
            Already have an account?{" "}
            <a href="/login" className="text-[#c4922a] font-medium hover:underline">Sign in</a>
          </p>
        </div>
      </div>
    </div>
  );
}
