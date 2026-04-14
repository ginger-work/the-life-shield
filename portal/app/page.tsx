"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

// ─── Icon Components ──────────────────────────────────────────────────────────

function IconShield() {
  return (
    <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function IconArrowRight() {
  return (
    <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
    </svg>
  );
}

function IconStar() {
  return (
    <svg width="14" height="14" fill="#c4922a" viewBox="0 0 24 24">
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}

// ─── Step Icons ───────────────────────────────────────────────────────────────

function IconClipboard() {
  return (
    <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function IconDocument() {
  return (
    <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function IconTrendUp() {
  return (
    <svg width="28" height="28" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  );
}

// ─── Nav ─────────────────────────────────────────────────────────────────────

function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? "bg-[#1a2744] shadow-lg" : "bg-[#1a2744]/95"
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-[#c4922a] rounded-lg flex items-center justify-center text-white">
            <IconShield />
          </div>
          <span className="text-white font-semibold text-base tracking-tight">The Life Shield</span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-[#8899bb] hover:text-white text-sm font-medium transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="bg-[#c4922a] hover:bg-[#d9a84e] text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
          >
            Get Started Free
          </Link>
        </div>
      </div>
    </nav>
  );
}

// ─── Hero Section ─────────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="bg-[#1a2744] pt-32 pb-24 px-6 relative overflow-hidden">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: `
            linear-gradient(rgba(196,146,42,0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(196,146,42,0.3) 1px, transparent 1px)
          `,
          backgroundSize: "60px 60px",
        }}
      />

      <div className="max-w-5xl mx-auto text-center relative z-10">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-[#c4922a]/15 border border-[#c4922a]/30 text-[#c4922a] px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-[#c4922a] inline-block" />
          FCRA & CROA Compliant Credit Restoration
        </div>

        {/* Headline */}
        <h1 className="text-5xl md:text-6xl font-bold text-white leading-tight tracking-tight mb-6">
          Fix Your Credit
          <br />
          <span className="text-[#c4922a]">In 30 Days.</span>
        </h1>

        {/* Subheadline */}
        <p className="text-xl text-[#a8b8d4] leading-relaxed max-w-2xl mx-auto mb-10">
          Attorney-backed credit repair with AI precision. We identify errors, file disputes,
          and fight for the score you deserve — all within federal law.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-14">
          <Link
            href="/register"
            className="bg-[#c4922a] hover:bg-[#d9a84e] text-white px-8 py-4 rounded-xl text-base font-semibold transition-all shadow-lg shadow-[#c4922a]/25 flex items-center gap-2 group"
          >
            Start Free Today
            <span className="group-hover:translate-x-0.5 transition-transform">
              <IconArrowRight />
            </span>
          </Link>
          <Link
            href="/login"
            className="border border-[#4a5e7a] hover:border-[#8899bb] text-[#a8b8d4] hover:text-white px-8 py-4 rounded-xl text-base font-medium transition-all"
          >
            Sign In to Portal
          </Link>
        </div>

        {/* Trust bar */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-8 text-sm text-[#6b84b0]">
          <div className="flex items-center gap-2">
            <span className="text-[#c4922a]"><IconCheck /></span>
            <span>No credit card required</span>
          </div>
          <div className="hidden sm:block w-px h-4 bg-[#2a3a5e]" />
          <div className="flex items-center gap-2">
            <span className="text-[#c4922a]"><IconCheck /></span>
            <span>30-day money-back guarantee</span>
          </div>
          <div className="hidden sm:block w-px h-4 bg-[#2a3a5e]" />
          <div className="flex items-center gap-2">
            <span className="text-[#c4922a]"><IconCheck /></span>
            <span>FCRA compliant process</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Stats Bar ────────────────────────────────────────────────────────────────

function StatsBar() {
  const stats = [
    { value: "127", label: "Average Points Added", suffix: " pts" },
    { value: "92", label: "Client Success Rate", suffix: "%" },
    { value: "30", label: "Day Average Timeline", suffix: " days" },
    { value: "10K+", label: "Errors Removed", suffix: "" },
  ];

  return (
    <section className="bg-[#0f1a30] border-b border-[#243358]">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((stat, i) => (
            <div key={i} className="text-center">
              <div className="text-3xl font-bold text-white">
                {stat.value}
                <span className="text-[#c4922a]">{stat.suffix}</span>
              </div>
              <div className="text-sm text-[#6b84b0] mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Value Props ──────────────────────────────────────────────────────────────

function ValueProps() {
  const props = [
    {
      title: "127 Points Average Increase",
      body: "Our clients gain an average of 127 credit score points through precise FCRA dispute strategies. Results backed by documented bureau outcomes.",
    },
    {
      title: "92% Client Success Rate",
      body: "Nine out of ten clients see measurable improvement within 30 days. We only file disputes we believe will succeed.",
    },
    {
      title: "100% FCRA Compliant",
      body: "Every dispute follows the Fair Credit Reporting Act to the letter. Attorney-backed letters filed directly with the three major bureaus.",
    },
    {
      title: "30-Day Money-Back Guarantee",
      body: "If you don't see progress within 30 days, we refund your plan fee — no questions asked. That's how confident we are.",
    },
  ];

  return (
    <section className="bg-white py-20 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-[#c4922a] text-sm font-semibold uppercase tracking-widest mb-3">Why The Life Shield</p>
          <h2 className="text-3xl md:text-4xl font-bold text-[#1a2744] leading-tight">
            Credit repair done right.
            <br />
            No shortcuts. No gimmicks.
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {props.map((p, i) => (
            <div key={i} className="border border-gray-100 rounded-xl p-7 hover:border-[#c4922a]/30 hover:shadow-md transition-all">
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 bg-[#c4922a]/10 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-[#c4922a]"><IconCheck /></span>
                </div>
                <div>
                  <h3 className="font-semibold text-[#1a2744] text-base mb-2">{p.title}</h3>
                  <p className="text-gray-500 text-sm leading-relaxed">{p.body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── How It Works ────────────────────────────────────────────────────────────

function HowItWorks() {
  const steps = [
    {
      number: "01",
      Icon: IconClipboard,
      title: "Create Your Account",
      body: "Register for free in under 2 minutes. No credit card required. We'll walk you through onboarding step-by-step.",
    },
    {
      number: "02",
      Icon: IconSearch,
      title: "We Pull Your Reports",
      body: "Our system performs a soft-pull credit analysis across all three bureaus — Equifax, Experian, and TransUnion — without affecting your score.",
    },
    {
      number: "03",
      Icon: IconDocument,
      title: "We File Disputes",
      body: "Tim Shaw, your AI credit advisor, identifies every disputable error and files attorney-backed dispute letters with each bureau.",
    },
    {
      number: "04",
      Icon: IconTrendUp,
      title: "Your Score Climbs",
      body: "Track your improvement in real time through your portal. Most clients see results in 30 days. We keep fighting until you're satisfied.",
    },
  ];

  return (
    <section className="bg-[#f4f6f9] py-20 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-[#c4922a] text-sm font-semibold uppercase tracking-widest mb-3">The Process</p>
          <h2 className="text-3xl md:text-4xl font-bold text-[#1a2744]">How it works</h2>
          <p className="text-gray-500 mt-4 max-w-xl mx-auto text-base">
            Four steps. Thirty days. A credit score you can be proud of.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <div key={i} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 relative">
              <div className="text-[#e8ecf2] text-5xl font-black absolute top-4 right-5 leading-none select-none">
                {step.number}
              </div>
              <div className="w-12 h-12 bg-[#1a2744] rounded-xl flex items-center justify-center text-[#c4922a] mb-5">
                <step.Icon />
              </div>
              <h3 className="font-semibold text-[#1a2744] text-base mb-2">{step.title}</h3>
              <p className="text-gray-500 text-sm leading-relaxed">{step.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Pricing ─────────────────────────────────────────────────────────────────

function Pricing() {
  const plans = [
    {
      name: "Free",
      price: 0,
      period: "forever",
      description: "Get started at no cost. See what's holding your score back.",
      features: [
        "Credit report analysis",
        "Score breakdown by bureau",
        "Dispute opportunity review",
        "Tim Shaw AI access (limited)",
        "Portal access",
      ],
      cta: "Start Free",
      href: "/register",
      featured: false,
    },
    {
      name: "Professional",
      price: 69,
      period: "per month",
      description: "Full dispute power. Most clients start here.",
      features: [
        "Everything in Free",
        "Unlimited dispute filings",
        "Tim Shaw AI 24/7 (full access)",
        "SMS progress notifications",
        "Weekly score tracking",
        "1 coaching session per month",
        "30-day money-back guarantee",
      ],
      cta: "Start Professional",
      href: "/register",
      featured: true,
    },
    {
      name: "Elite",
      price: 129,
      period: "per month",
      description: "Maximum power for complex credit situations.",
      features: [
        "Everything in Professional",
        "Daily credit monitoring",
        "2 coaching sessions per month",
        "Video consultations",
        "Identity theft protection",
        "Priority dispute processing",
        "Dedicated case manager",
      ],
      cta: "Start Elite",
      href: "/register",
      featured: false,
    },
  ];

  return (
    <section className="bg-white py-20 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-[#c4922a] text-sm font-semibold uppercase tracking-widest mb-3">Pricing</p>
          <h2 className="text-3xl md:text-4xl font-bold text-[#1a2744]">
            Transparent pricing. No surprises.
          </h2>
          <p className="text-gray-500 mt-4 max-w-xl mx-auto text-base">
            Start free. Upgrade when you're ready. Cancel any time.
            All plans include a 30-day money-back guarantee.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {plans.map((plan, i) => (
            <div
              key={i}
              className={`rounded-xl p-7 border-2 relative ${
                plan.featured
                  ? "bg-[#1a2744] border-[#c4922a] shadow-2xl shadow-[#1a2744]/20 md:-mt-4"
                  : "bg-white border-gray-100 shadow-sm"
              }`}
            >
              {plan.featured && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span className="bg-[#c4922a] text-white px-4 py-1 rounded-full text-xs font-bold uppercase tracking-wider">
                    Most Popular
                  </span>
                </div>
              )}

              <div className="mb-6">
                <h3 className={`font-bold text-lg ${plan.featured ? "text-white" : "text-[#1a2744]"}`}>
                  {plan.name}
                </h3>
                <p className={`text-sm mt-1 ${plan.featured ? "text-[#8899bb]" : "text-gray-400"}`}>
                  {plan.description}
                </p>
                <div className="mt-4 flex items-end gap-1">
                  <span className={`text-4xl font-black ${plan.featured ? "text-white" : "text-[#1a2744]"}`}>
                    ${plan.price}
                  </span>
                  <span className={`text-sm mb-1.5 ${plan.featured ? "text-[#6b84b0]" : "text-gray-400"}`}>
                    /{plan.period}
                  </span>
                </div>
              </div>

              <ul className="space-y-3 mb-7">
                {plan.features.map((feature, j) => (
                  <li key={j} className="flex items-start gap-2.5 text-sm">
                    <span className={`mt-0.5 flex-shrink-0 ${plan.featured ? "text-[#c4922a]" : "text-[#0d7a6e]"}`}>
                      <IconCheck />
                    </span>
                    <span className={plan.featured ? "text-[#a8b8d4]" : "text-gray-600"}>
                      {feature}
                    </span>
                  </li>
                ))}
              </ul>

              <Link
                href={plan.href}
                className={`block w-full text-center py-3 rounded-xl text-sm font-semibold transition-all ${
                  plan.featured
                    ? "bg-[#c4922a] hover:bg-[#d9a84e] text-white shadow-lg shadow-[#c4922a]/25"
                    : "border border-[#1a2744] text-[#1a2744] hover:bg-[#1a2744] hover:text-white"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-gray-400 mt-8">
          Prices shown in USD. CROA-compliant — no advance fees collected before services begin.
          Cancel any time with 30-day money-back protection.
        </p>
      </div>
    </section>
  );
}

// ─── Testimonials ────────────────────────────────────────────────────────────

function Testimonials() {
  const testimonials = [
    {
      quote: "My score jumped 143 points in 28 days. Deleted two collections and a false charge-off. I couldn't believe it.",
      name: "Marcus T.",
      location: "Charlotte, NC",
      score: "+143 pts",
    },
    {
      quote: "Tim Shaw walked me through every dispute. I always knew exactly where things stood. Professional from start to finish.",
      name: "Denise R.",
      location: "Atlanta, GA",
      score: "+98 pts",
    },
    {
      quote: "Three other companies failed. The Life Shield got my mortgage-ready score in 6 weeks. Bought my house last month.",
      name: "James W.",
      location: "Raleigh, NC",
      score: "+119 pts",
    },
  ];

  return (
    <section className="bg-[#f4f6f9] py-20 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-[#c4922a] text-sm font-semibold uppercase tracking-widest mb-3">Client Results</p>
          <h2 className="text-3xl md:text-4xl font-bold text-[#1a2744]">Real people. Real scores.</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((t, i) => (
            <div key={i} className="bg-white rounded-xl p-7 shadow-sm border border-gray-100">
              {/* Stars */}
              <div className="flex gap-0.5 mb-5">
                {[0,1,2,3,4].map((s) => <IconStar key={s} />)}
              </div>

              <blockquote className="text-gray-700 text-sm leading-relaxed mb-6">
                "{t.quote}"
              </blockquote>

              <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                <div>
                  <p className="font-semibold text-[#1a2744] text-sm">{t.name}</p>
                  <p className="text-gray-400 text-xs">{t.location}</p>
                </div>
                <div className="bg-[#0d7a6e]/10 text-[#0d7a6e] text-sm font-bold px-3 py-1 rounded-full">
                  {t.score}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Trust Section ────────────────────────────────────────────────────────────

function TrustSection() {
  const badges = [
    { label: "FCRA Compliant", sub: "Federal law compliance" },
    { label: "CROA Certified", sub: "Credit Repair Organizations Act" },
    { label: "Attorney Backed", sub: "Licensed counsel on every case" },
    { label: "256-bit Encrypted", sub: "Bank-level data security" },
    { label: "30-Day Guarantee", sub: "Full refund if no progress" },
  ];

  return (
    <section className="bg-[#1a2744] py-16 px-6">
      <div className="max-w-6xl mx-auto">
        <p className="text-center text-[#6b84b0] text-sm mb-8 uppercase tracking-widest font-medium">
          Your protection — built in from day one
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          {badges.map((b, i) => (
            <div
              key={i}
              className="bg-[#243358] border border-[#2a3a5e] rounded-lg px-5 py-3 text-center min-w-[160px]"
            >
              <p className="text-white font-semibold text-sm">{b.label}</p>
              <p className="text-[#6b84b0] text-xs mt-0.5">{b.sub}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Final CTA ────────────────────────────────────────────────────────────────

function FinalCTA() {
  return (
    <section className="bg-white py-24 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-4xl font-bold text-[#1a2744] leading-tight mb-5">
          Your credit score is
          <br />
          fixable. Start today.
        </h2>
        <p className="text-gray-500 text-lg mb-10 leading-relaxed">
          Join thousands of clients who've taken back control of their financial future.
          It starts with one free account.
        </p>

        <Link
          href="/register"
          className="inline-flex items-center gap-2.5 bg-[#1a2744] hover:bg-[#243358] text-white px-10 py-4 rounded-xl text-base font-semibold transition-all shadow-xl group"
        >
          Create Free Account
          <span className="group-hover:translate-x-0.5 transition-transform">
            <IconArrowRight />
          </span>
        </Link>

        <p className="text-gray-400 text-sm mt-5">
          No credit card required &bull; 30-day money-back guarantee &bull; Cancel any time
        </p>
      </div>
    </section>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function Footer() {
  return (
    <footer className="bg-[#0f1a30] border-t border-[#243358] py-10 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-[#c4922a] rounded-md flex items-center justify-center text-white">
            <IconShield />
          </div>
          <span className="text-white font-semibold text-sm">The Life Shield</span>
        </div>

        <p className="text-[#4a5e7a] text-xs text-center leading-relaxed max-w-lg">
          The Life Shield is a credit repair organization operating under CROA and FCRA compliance requirements.
          Results vary. Past performance does not guarantee future outcomes.
          Attorney-backed services available in all 50 states.
        </p>

        <div className="flex gap-5">
          <Link href="/login" className="text-[#4a5e7a] hover:text-white text-xs transition-colors">
            Sign In
          </Link>
          <Link href="/register" className="text-[#4a5e7a] hover:text-white text-xs transition-colors">
            Register
          </Link>
        </div>
      </div>
    </footer>
  );
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <Nav />
      <Hero />
      <StatsBar />
      <ValueProps />
      <HowItWorks />
      <Pricing />
      <Testimonials />
      <TrustSection />
      <FinalCTA />
      <Footer />
    </div>
  );
}
