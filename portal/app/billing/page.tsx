"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { api, Subscription, SubscriptionPlan, Payment } from "@/lib/api";

const MOCK_SUBSCRIPTION: Subscription = {
  id: "sub_1",
  plan_id: "premium",
  plan_name: "Premium",
  price_monthly: 79.99,
  status: "active",
  started_at: new Date(Date.now() - 86400000 * 30).toISOString(),
  next_billing_at: new Date(Date.now() + 86400000 * 15).toISOString(),
  features: [
    "Unlimited disputes",
    "Tim Shaw AI chat (24/7)",
    "SMS notifications",
    "Weekly score updates",
    "1 coaching session/month",
    "Priority support",
  ],
};

const MOCK_PAYMENTS: Payment[] = [
  { id: "p1", amount: 79.99, description: "Premium Plan - Monthly", status: "completed", paid_at: new Date(Date.now() - 86400000 * 30).toISOString() },
  { id: "p2", amount: 79.99, description: "Premium Plan - Monthly", status: "completed", paid_at: new Date(Date.now() - 86400000 * 60).toISOString() },
  { id: "p3", amount: 29.99, description: "Credit Foundations Guide", status: "completed", paid_at: new Date(Date.now() - 86400000 * 45).toISOString() },
];

const MOCK_PLANS: SubscriptionPlan[] = [
  { id: "basic", name: "Basic", price_monthly: 29.99, features: ["Credit report analysis", "Up to 3 disputes", "Email support", "Monthly score update"] },
  { id: "premium", name: "Premium", price_monthly: 79.99, features: ["Unlimited disputes", "Tim Shaw AI 24/7", "SMS notifications", "Weekly scores", "1 coaching/month"] },
  { id: "vip", name: "VIP", price_monthly: 199.99, features: ["Everything in Premium", "Daily monitoring", "2 coaching/month", "Video sessions", "Identity theft protection"] },
];

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription>(MOCK_SUBSCRIPTION);
  const [payments, setPayments] = useState<Payment[]>(MOCK_PAYMENTS);
  const [plans, setPlans] = useState<SubscriptionPlan[]>(MOCK_PLANS);
  const [showCancel, setShowCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Billing" />
        <main className="flex-1 p-6 space-y-6">
          {/* Current plan */}
          <div className="bg-[#1a2744] text-white rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[#c4922a] text-sm font-semibold uppercase tracking-wide">Current Plan</p>
                <h2 className="text-2xl font-bold mt-1">{subscription.plan_name}</h2>
                <p className="text-3xl font-bold mt-2">
                  ${subscription.price_monthly}
                  <span className="text-base font-normal text-gray-300">/month</span>
                </p>
              </div>
              <div className="text-right">
                <span className="bg-green-500 text-white px-3 py-1 rounded-full text-sm font-semibold">Active</span>
                <p className="text-gray-300 text-sm mt-2">
                  Next billing: {subscription.next_billing_at
                    ? new Date(subscription.next_billing_at).toLocaleDateString()
                    : "—"}
                </p>
              </div>
            </div>

            {/* Features */}
            <div className="mt-4 grid grid-cols-2 gap-1">
              {subscription.features.map((f) => (
                <div key={f} className="flex items-center gap-2 text-sm text-gray-300">
                  <span className="text-[#c4922a]">✓</span>
                  <span>{f}</span>
                </div>
              ))}
            </div>

            {/* Payment method */}
            <div className="mt-4 pt-4 border-t border-white/20 flex items-center gap-3">
              <div className="w-10 h-6 bg-[#2a3a5e] rounded flex items-center justify-center text-xs font-bold">VISA</div>
              <span className="text-sm text-gray-300">•••• •••• •••• 4242</span>
              <button className="ml-auto text-[#c4922a] text-sm hover:underline">Update</button>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button className="flex-1 bg-white border border-[#c4922a] text-[#c4922a] py-2.5 rounded-lg font-medium hover:bg-[#c4922a]/5">
              ⬆️ Upgrade Plan
            </button>
            <button
              onClick={() => setShowCancel(true)}
              className="flex-1 bg-white border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium hover:bg-gray-50"
            >
              Cancel Subscription
            </button>
          </div>

          {/* Available plans */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Available Plans</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {plans.map((plan) => (
                <div
                  key={plan.id}
                  className={`bg-white rounded-xl p-5 border-2 shadow-sm ${
                    plan.id === subscription.plan_id
                      ? "border-[#c4922a]"
                      : "border-gray-100"
                  }`}
                >
                  {plan.id === subscription.plan_id && (
                    <span className="text-xs bg-[#c4922a] text-white px-2 py-0.5 rounded-full font-semibold">Current</span>
                  )}
                  <h3 className="font-bold text-[#1a2744] mt-2">{plan.name}</h3>
                  <p className="text-2xl font-bold text-[#1a2744] mt-1">
                    ${plan.price_monthly}<span className="text-sm font-normal text-gray-400">/mo</span>
                  </p>
                  <ul className="mt-3 space-y-1">
                    {plan.features.map((f) => (
                      <li key={f} className="text-xs text-gray-600 flex gap-1.5">
                        <span className="text-[#0d7a6e]">✓</span>{f}
                      </li>
                    ))}
                  </ul>
                  {plan.id !== subscription.plan_id && (
                    <button className="mt-4 w-full bg-[#1a2744] text-white py-2 rounded-lg text-sm font-medium hover:bg-[#2a3a5e]">
                      {parseFloat(plan.price_monthly.toString()) > subscription.price_monthly ? "Upgrade" : "Downgrade"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Billing history */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Billing History</h2>
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              {payments.map((payment) => (
                <div key={payment.id} className="flex items-center justify-between p-4 border-b border-gray-50 last:border-0">
                  <div>
                    <p className="font-medium text-[#1a2744] text-sm">{payment.description}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {payment.paid_at ? new Date(payment.paid_at).toLocaleDateString() : "—"}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-[#1a2744]">${payment.amount.toFixed(2)}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      payment.status === "completed" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                    }`}>
                      {payment.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </main>
      </div>

      {/* Cancel modal */}
      {showCancel && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-lg font-bold text-[#1a2744] mb-1">Cancel Subscription?</h3>
            <p className="text-gray-500 text-sm mb-4">
              You'll keep access until {subscription.next_billing_at
                ? new Date(subscription.next_billing_at).toLocaleDateString()
                : "end of billing period"}.
            </p>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason (optional)</label>
            <textarea
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="Help us improve..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-4 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-red-400"
            />
            <div className="flex gap-3">
              <button onClick={() => setShowCancel(false)} className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium">
                Keep My Plan
              </button>
              <button
                onClick={() => {
                  setShowCancel(false);
                  alert("Subscription cancelled. You'll have access until your next billing date.");
                }}
                className="flex-1 bg-red-600 text-white py-2.5 rounded-lg font-medium hover:bg-red-700"
              >
                Confirm Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
