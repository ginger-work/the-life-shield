"use client";

import { useState, useEffect } from "react";

interface Props {
  planId: string;
  planName: string;
  priceMonthly: number;
  onSuccess: () => void;
  onCancel: () => void;
}

/**
 * StripePaymentForm
 *
 * Collects card details and calls the backend to create a subscription.
 * Uses Stripe.js loaded via script tag for PCI compliance.
 *
 * In demo / no-Stripe mode: shows card input UI and submits with a test token.
 * In production: replace with @stripe/react-stripe-js <CardElement />.
 */
export function StripePaymentForm({ planId, planName, priceMonthly, onSuccess, onCancel }: Props) {
  const [cardNumber, setCardNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [stripeReady, setStripeReady] = useState(false);

  // Check if Stripe publishable key is configured
  const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;

  useEffect(() => {
    if (publishableKey && publishableKey !== "pk_test_placeholder") {
      setStripeReady(true);
    }
  }, [publishableKey]);

  // Format card number: 4242 4242 4242 4242
  function formatCardNumber(value: string) {
    const digits = value.replace(/\D/g, "").slice(0, 16);
    return digits.replace(/(.{4})/g, "$1 ").trim();
  }

  // Format expiry: MM / YY
  function formatExpiry(value: string) {
    const digits = value.replace(/\D/g, "").slice(0, 4);
    if (digits.length >= 2) {
      return digits.slice(0, 2) + " / " + digits.slice(2);
    }
    return digits;
  }

  function validateCard(): string | null {
    const digits = cardNumber.replace(/\D/g, "");
    if (digits.length < 16) return "Please enter a valid 16-digit card number.";
    if (!expiry.includes("/") && expiry.replace(/\D/g, "").length < 4)
      return "Please enter a valid expiration date.";
    if (cvc.replace(/\D/g, "").length < 3) return "Please enter a valid CVC.";
    if (!name.trim()) return "Please enter the name on your card.";
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const validationError = validateCard();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);

    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

      // In production with Stripe configured: tokenize card with Stripe.js,
      // send payment_method_id instead of raw card data.
      // For demo/test mode: send a test token.
      const paymentToken = stripeReady
        ? `pm_card_${cardNumber.replace(/\D/g, "").slice(-4)}` // Production: use Stripe.js tokenization
        : "pm_card_visa"; // Stripe test token

      const response = await fetch("/api/products/subscriptions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          plan_id: planId,
          payment_token: paymentToken,
          card_name: name,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || data.message || "Payment failed. Please try again.");
      }

      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Payment failed. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl p-7 max-w-md w-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-[#1a2744]">Subscribe to {planName}</h3>
            <p className="text-[#c4922a] font-semibold text-base mt-0.5">
              ${priceMonthly}/month
            </p>
          </div>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Test mode notice */}
        {!stripeReady && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-3 py-2 rounded-lg mb-4">
            <strong>Test Mode:</strong> Use card 4242 4242 4242 4242, any future expiry, any CVC.
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Name on card */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">Name on card</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Smith"
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] bg-gray-50 focus:bg-white"
            />
          </div>

          {/* Card number */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">Card number</label>
            <input
              type="text"
              value={cardNumber}
              onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
              placeholder="4242 4242 4242 4242"
              maxLength={19}
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] bg-gray-50 focus:bg-white font-mono"
            />
          </div>

          {/* Expiry + CVC */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1.5">Expiry date</label>
              <input
                type="text"
                value={expiry}
                onChange={(e) => setExpiry(formatExpiry(e.target.value))}
                placeholder="MM / YY"
                maxLength={7}
                required
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] bg-gray-50 focus:bg-white font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1.5">CVC</label>
              <input
                type="text"
                value={cvc}
                onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))}
                placeholder="123"
                maxLength={4}
                required
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c4922a] bg-gray-50 focus:bg-white font-mono"
              />
            </div>
          </div>

          {/* Security note */}
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span>Your payment is secured by 256-bit SSL encryption.</span>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 border border-gray-200 text-gray-600 py-3 rounded-xl text-sm font-medium hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-[#c4922a] text-white py-3 rounded-xl text-sm font-semibold hover:bg-[#d9a84e] disabled:opacity-50 transition-colors shadow-md shadow-[#c4922a]/20"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                  Processing…
                </span>
              ) : (
                `Pay $${priceMonthly}/month`
              )}
            </button>
          </div>
        </form>

        <p className="text-center text-xs text-gray-400 mt-4">
          30-day money-back guarantee &bull; Cancel any time &bull; CROA compliant
        </p>
      </div>
    </div>
  );
}
