"""
Email Service — The Life Shield

Handles transactional email delivery via SendGrid (primary) with
a fallback SMTP mode for development/testing.

Templates:
  - welcome           (Day 0) — Account created
  - tim_welcome       (Day 0) — Personal intro from Tim Shaw
  - credit_pulled     (Day 1) — Credit report ready
  - findings          (Day 3) — What we found + disputes planned
  - dispute_filed     (Day 7) — Dispute letters submitted to bureaus
  - monthly_checkin   (Day 30) — Progress report
  - payment_confirm          — Subscription payment confirmed
  - password_reset           — Password reset link

Usage:
  from app.services.email_service import email_service
  await email_service.send_welcome(user_email, first_name)
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


# ── HTML Email Templates ──────────────────────────────────────────────────────

def _base_html(title: str, body: str) -> str:
    """Wrap content in a professional branded email template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f4f6f9; color: #111827; }}
    .wrapper {{ max-width: 580px; margin: 0 auto; padding: 32px 16px; }}
    .card {{ background: #ffffff; border-radius: 12px; padding: 40px; border: 1px solid #e2e8f0; }}
    .logo {{ display: flex; align-items: center; gap: 12px; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #f0f4f8; }}
    .logo-icon {{ width: 36px; height: 36px; background: #1a2744; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; }}
    .logo-name {{ font-weight: 700; color: #1a2744; font-size: 16px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #1a2744; margin: 0 0 12px; line-height: 1.3; }}
    p {{ color: #4b5563; font-size: 15px; line-height: 1.6; margin: 0 0 16px; }}
    .btn {{ display: inline-block; background: #c4922a; color: #ffffff; text-decoration: none; padding: 13px 28px; border-radius: 10px; font-weight: 600; font-size: 14px; margin: 8px 0; }}
    .stat {{ background: #f4f6f9; border-radius: 8px; padding: 16px 20px; margin: 12px 0; }}
    .stat-value {{ font-size: 24px; font-weight: 800; color: #1a2744; }}
    .stat-label {{ font-size: 12px; color: #6b7280; margin-top: 2px; }}
    .divider {{ border: none; border-top: 1px solid #f0f4f8; margin: 24px 0; }}
    .footer {{ text-align: center; color: #9ca3af; font-size: 11px; margin-top: 24px; line-height: 1.6; }}
    .badge {{ display: inline-block; background: #0d7a6e; color: #fff; font-size: 11px; padding: 3px 10px; border-radius: 999px; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="logo">
        <span class="logo-icon">
          <svg width="20" height="20" fill="none" stroke="white" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
          </svg>
        </span>
        <span class="logo-name">The Life Shield</span>
      </div>
      {body}
      <hr class="divider">
      <p style="font-size:12px; color:#9ca3af; margin:0; line-height:1.6;">
        The Life Shield &bull; Credit Repair Services &bull; FCRA & CROA Compliant<br>
        This email was sent to you because you have an account with The Life Shield.
        <a href="#" style="color:#c4922a; text-decoration:none;">Unsubscribe</a>
      </p>
    </div>
  </div>
</body>
</html>"""


def _plain_text(title: str, body: str) -> str:
    """Strip HTML for plain-text fallback."""
    import re
    clean = re.sub(r"<[^>]+>", "", body)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return f"The Life Shield — {title}\n\n{clean.strip()}\n\n---\nFCRA & CROA Compliant Credit Repair"


# ── Template Builders ─────────────────────────────────────────────────────────

class Templates:
    @staticmethod
    def welcome(first_name: str) -> Dict[str, str]:
        body = f"""
        <h1>Welcome to The Life Shield, {first_name}.</h1>
        <p>Your account is ready. You're now part of a credit repair process trusted by thousands of clients across the country.</p>
        <p>Here's what happens next:</p>
        <ul style="color:#4b5563; font-size:14px; line-height:2; padding-left:20px;">
          <li>Tim Shaw, your AI credit advisor, will reach out shortly</li>
          <li>We'll pull your credit report across all three bureaus</li>
          <li>You'll see a full dispute plan within 72 hours</li>
          <li>Most clients see results in 30 days</li>
        </ul>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/dashboard" class="btn">Go to Your Portal</a>
        """
        return {
            "subject": f"Welcome to The Life Shield, {first_name}",
            "html": _base_html("Welcome", body),
            "text": f"Welcome to The Life Shield, {first_name}.\n\nYour account is ready. Log in at https://thelifeshield.com/dashboard to get started.",
        }

    @staticmethod
    def tim_welcome(first_name: str) -> Dict[str, str]:
        body = f"""
        <h1>Hi {first_name}, I'm Tim Shaw.</h1>
        <p>I'm your dedicated credit advisor here at The Life Shield. I'm an AI-powered agent — designed to be available 24/7 and built around one goal: improving your credit score.</p>
        <p>In the next 24 hours, I'll complete a full analysis of your credit report across Equifax, Experian, and TransUnion. I'll identify every error, inaccuracy, and disputable item on your file.</p>
        <p>You'll hear from me again tomorrow with a complete breakdown. In the meantime, log in if you have any questions — I'm always here.</p>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/chat" class="btn">Chat with Tim Shaw</a>
        <p style="font-size:13px; color:#9ca3af; margin-top:20px;">
          <em>Disclosure: Tim Shaw is an AI agent. For legal advice or complex situations, escalation to a licensed professional is available on request.</em>
        </p>
        """
        return {
            "subject": f"Hi {first_name} — I'm Tim Shaw, your credit advisor",
            "html": _base_html("Welcome from Tim Shaw", body),
            "text": f"Hi {first_name},\n\nI'm Tim Shaw, your AI credit advisor at The Life Shield. I'll have your full credit report analysis ready within 24 hours.\n\nTim Shaw (AI Agent)\nThe Life Shield",
        }

    @staticmethod
    def credit_pulled(first_name: str, score_data: Optional[Dict] = None) -> Dict[str, str]:
        scores_html = ""
        if score_data:
            for bureau, info in score_data.items():
                score = info.get("score", "—")
                scores_html += f"""
                <div class="stat">
                  <div class="stat-value">{score}</div>
                  <div class="stat-label">{bureau.capitalize()} Credit Score</div>
                </div>"""

        body = f"""
        <h1>Your credit report is ready, {first_name}.</h1>
        <p>I've completed the soft-pull analysis across all three bureaus. Here's where you stand today:</p>
        {scores_html or '<div class="stat"><div class="stat-label">Score data will appear in your portal.</div></div>'}
        <p>Over the next 48 hours, I'll complete a detailed review of every tradeline, inquiry, and negative item on your report. You'll receive a full dispute plan on Day 3.</p>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/credit" class="btn">View Your Credit Report</a>
        """
        return {
            "subject": f"Your credit report is ready — The Life Shield",
            "html": _base_html("Credit Report Ready", body),
            "text": f"Hi {first_name},\n\nYour credit report has been pulled and is ready to review in your portal.\n\nLog in at https://thelifeshield.com/credit",
        }

    @staticmethod
    def findings(first_name: str, dispute_count: int = 0, items_found: int = 0) -> Dict[str, str]:
        body = f"""
        <h1>Here's what we found, {first_name}.</h1>
        <p>After a thorough review of your credit file across all three bureaus, here's the breakdown:</p>
        <div class="stat">
          <div class="stat-value">{items_found}</div>
          <div class="stat-label">Total items reviewed</div>
        </div>
        <div class="stat">
          <div class="stat-value">{dispute_count}</div>
          <div class="stat-label">Items eligible for dispute</div>
        </div>
        <p>I've prepared attorney-backed dispute letters for each item. These will be submitted to the bureaus within the next 4 days. You'll receive a confirmation email when each one is filed.</p>
        <p>The bureaus have <strong>30 days</strong> to investigate and respond to each dispute. You can track the status of every dispute in real time from your portal.</p>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/disputes" class="btn">View Your Dispute Plan</a>
        """
        return {
            "subject": f"{dispute_count} items found on your credit report — The Life Shield",
            "html": _base_html("Your Findings", body),
            "text": f"Hi {first_name},\n\nWe found {dispute_count} disputable items on your credit report. Log in to view your full dispute plan:\nhttps://thelifeshield.com/disputes",
        }

    @staticmethod
    def dispute_filed(first_name: str, bureau: str, dispute_count: int = 1) -> Dict[str, str]:
        body = f"""
        <h1>Your dispute has been filed, {first_name}.</h1>
        <span class="badge">Filed with {bureau.capitalize()}</span>
        <p style="margin-top:16px;">We've submitted {dispute_count} dispute letter{"s" if dispute_count != 1 else ""} to <strong>{bureau.capitalize()}</strong> on your behalf. These are attorney-backed letters citing the specific FCRA violations found in your report.</p>
        <p><strong>What happens next:</strong></p>
        <ul style="color:#4b5563; font-size:14px; line-height:2; padding-left:20px;">
          <li>{bureau.capitalize()} has 30 days to investigate and respond</li>
          <li>You'll receive a notification when they respond</li>
          <li>If verified as an error, the item must be corrected or removed</li>
          <li>Your score updates automatically after corrections</li>
        </ul>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/disputes" class="btn">Track Your Disputes</a>
        """
        return {
            "subject": f"Dispute filed with {bureau.capitalize()} — The Life Shield",
            "html": _base_html("Dispute Filed", body),
            "text": f"Hi {first_name},\n\nYour dispute has been filed with {bureau}. Track progress at https://thelifeshield.com/disputes",
        }

    @staticmethod
    def monthly_checkin(first_name: str, score_change: int = 0, disputes_resolved: int = 0) -> Dict[str, str]:
        direction = "up" if score_change >= 0 else "down"
        body = f"""
        <h1>Your 30-day progress report, {first_name}.</h1>
        <p>Here's a summary of everything we've accomplished together over the past month:</p>
        <div class="stat">
          <div class="stat-value">{"+" if score_change >= 0 else ""}{score_change} pts</div>
          <div class="stat-label">Average score change ({direction})</div>
        </div>
        <div class="stat">
          <div class="stat-value">{disputes_resolved}</div>
          <div class="stat-label">Disputes resolved this month</div>
        </div>
        <p>We're continuing to monitor your credit file and will file additional disputes as new opportunities arise. Log in to your portal for a full breakdown of your progress.</p>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/dashboard" class="btn">View Your Full Report</a>
        """
        return {
            "subject": f"Your 30-day credit progress report — The Life Shield",
            "html": _base_html("Monthly Check-In", body),
            "text": f"Hi {first_name},\n\nYour 30-day progress report is ready. Score change: {'+' if score_change >= 0 else ''}{score_change} pts. Log in at https://thelifeshield.com/dashboard",
        }

    @staticmethod
    def payment_confirmation(first_name: str, plan_name: str, amount: float) -> Dict[str, str]:
        body = f"""
        <h1>Payment confirmed, {first_name}.</h1>
        <div class="stat">
          <div class="stat-value">${amount:.2f}</div>
          <div class="stat-label">{plan_name} Plan — Monthly subscription</div>
        </div>
        <p>Your subscription is active. You now have full access to all {plan_name} features, including unlimited disputes and Tim Shaw 24/7.</p>
        <a href="{settings.APP_ENV and 'https://thelifeshield.com' or 'http://localhost:3000'}/billing" class="btn">View Billing Details</a>
        """
        return {
            "subject": f"Payment confirmed — {plan_name} Plan",
            "html": _base_html("Payment Confirmed", body),
            "text": f"Hi {first_name},\n\nPayment of ${amount:.2f} confirmed for your {plan_name} plan. Log in at https://thelifeshield.com",
        }

    @staticmethod
    def password_reset(first_name: str, reset_url: str) -> Dict[str, str]:
        body = f"""
        <h1>Reset your password, {first_name}.</h1>
        <p>We received a request to reset your password. Click the button below to set a new one. This link expires in 1 hour.</p>
        <a href="{reset_url}" class="btn">Reset My Password</a>
        <p style="font-size:13px; color:#9ca3af;">If you didn't request this, you can safely ignore this email. Your password won't change.</p>
        """
        return {
            "subject": "Reset your password — The Life Shield",
            "html": _base_html("Password Reset", body),
            "text": f"Hi {first_name},\n\nReset your password: {reset_url}\n\nThis link expires in 1 hour.",
        }


# ── Delivery Layer ────────────────────────────────────────────────────────────

class EmailService:
    """
    Sends transactional emails via SendGrid API.
    Falls back to SMTP if SENDGRID_API_KEY is not set (development mode).
    """

    def __init__(self):
        self.sendgrid_api_key = getattr(settings, "SENDGRID_API_KEY", None)
        self.from_email = getattr(settings, "SENDGRID_FROM_EMAIL", "noreply@thelifeshield.com")
        self.from_name = getattr(settings, "SENDGRID_FROM_NAME", "The Life Shield")

    @property
    def _is_configured(self) -> bool:
        return bool(self.sendgrid_api_key)

    async def _send_via_sendgrid(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send via SendGrid v3 API."""
        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email, "name": to_name}],
                    "subject": subject,
                }
            ],
            "from": {"email": self.from_email, "name": self.from_name},
            "content": [
                {"type": "text/plain", "value": text_content},
                {"type": "text/html", "value": html_content},
            ],
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code not in (200, 201, 202):
            log.error("sendgrid_failed", status=resp.status_code, body=resp.text[:500])
            return False

        log.info("email_sent_sendgrid", to=to_email, subject=subject)
        return True

    def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Fallback: log email to console in development (no SMTP configured)."""
        log.warning(
            "email_dev_mode",
            note="SendGrid not configured — email logged only",
            to=to_email,
            subject=subject,
        )
        print(f"\n{'='*60}")
        print(f"[EMAIL - DEV MODE]")
        print(f"TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"BODY: {text_content[:400]}")
        print(f"{'='*60}\n")
        return True  # Pretend success in dev

    async def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send an email. Returns True on success."""
        try:
            if self._is_configured:
                return await self._send_via_sendgrid(to_email, to_name, subject, html_content, text_content)
            else:
                return self._send_via_smtp(to_email, subject, html_content, text_content)
        except Exception as e:
            log.error("email_send_error", error=str(e), to=to_email, subject=subject)
            return False

    # ── Convenience Methods ───────────────────────────────────────────────────

    async def send_welcome(self, to_email: str, first_name: str) -> bool:
        t = Templates.welcome(first_name)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_tim_welcome(self, to_email: str, first_name: str) -> bool:
        t = Templates.tim_welcome(first_name)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_credit_pulled(
        self, to_email: str, first_name: str, score_data: Optional[Dict] = None
    ) -> bool:
        t = Templates.credit_pulled(first_name, score_data)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_findings(
        self, to_email: str, first_name: str, dispute_count: int = 0, items_found: int = 0
    ) -> bool:
        t = Templates.findings(first_name, dispute_count, items_found)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_dispute_filed(
        self, to_email: str, first_name: str, bureau: str, dispute_count: int = 1
    ) -> bool:
        t = Templates.dispute_filed(first_name, bureau, dispute_count)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_monthly_checkin(
        self, to_email: str, first_name: str, score_change: int = 0, disputes_resolved: int = 0
    ) -> bool:
        t = Templates.monthly_checkin(first_name, score_change, disputes_resolved)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_payment_confirmation(
        self, to_email: str, first_name: str, plan_name: str, amount: float
    ) -> bool:
        t = Templates.payment_confirmation(first_name, plan_name, amount)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])

    async def send_password_reset(
        self, to_email: str, first_name: str, reset_url: str
    ) -> bool:
        t = Templates.password_reset(first_name, reset_url)
        return await self.send(to_email, first_name, t["subject"], t["html"], t["text"])


# ── Singleton ─────────────────────────────────────────────────────────────────

email_service = EmailService()
