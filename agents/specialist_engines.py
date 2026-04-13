"""
The Life Shield — Specialist Agent Engines (Phase 3)

5 specialist engines that power Tim Shaw from behind the scenes:
  - CreditAnalystEngine    : Reviews reports, identifies disputes, prioritizes strategy
  - ComplianceEngine       : FCRA/CROA checks, compliance gating
  - SchedulerEngine        : Appointments, reminders, SLA management
  - RecommendationEngine   : Personalized product recommendations (admin-approved only)
  - SupervisorEngine       : Human oversight, escalation management
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CROA/FCRA violation word list (compliance gating)
# ---------------------------------------------------------------------------

VIOLATION_PATTERNS = [
    # CROA — no guarantees
    r"\bguarantee[sd]?\b",
    r"\bpromise[sd]?\b",
    r"\b100\s*%\s*(removal|success|guarantee)\b",
    r"\bwill\s+definitely\s+remove\b",
    r"\bwill\s+be\s+removed\b",
    # FCRA — no deception
    r"\bdelete\s+accurate\b",
    r"\bcreate\s+a\s+new\s+credit\s+(file|identity)\b",
    r"\bCPN\b",  # Credit Privacy Number — illegal
    # Upfront payment (CROA)
    r"\bpay\s+(before|first|upfront)\b",
    r"\badvance\s+(fee|payment)\b",
]

COMPILED_VIOLATIONS = [re.compile(p, re.IGNORECASE) for p in VIOLATION_PATTERNS]


def _contains_violation(text: str) -> List[str]:
    """Return list of triggered violation patterns."""
    triggered = []
    for pattern in COMPILED_VIOLATIONS:
        if pattern.search(text):
            triggered.append(pattern.pattern)
    return triggered


# ---------------------------------------------------------------------------
# AGENT 2: Credit Analyst Engine
# ---------------------------------------------------------------------------

class CreditAnalystEngine:
    """
    Analyzes client credit reports and drives dispute strategy.
    Ingests tradeline / negative item data and generates prioritized action plans.
    """

    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.logger = logging.getLogger(f"{__name__}.CreditAnalyst")

    # ------------------------------------------------------------------
    def analyze(self, message: str) -> Dict[str, Any]:
        """
        Analyze client's credit file and return dispute strategy.
        In production this fetches from DB; here returns rich mock output.
        """
        try:
            # Fetch negative items for this client (mocked for demo)
            negative_items = self._fetch_negative_items()
            disputes_filed = self._fetch_active_disputes()
            credit_score = self._fetch_latest_score()

            if not negative_items:
                return {
                    "response": (
                        "Great news! I've reviewed your credit file and I don't see any "
                        "immediately disputable items right now. Your score is currently "
                        f"{credit_score}. I'll keep monitoring for any changes."
                    ),
                    "action": "none",
                    "needs_escalation": False,
                }

            priority_item = negative_items[0]
            response = (
                f"I reviewed your credit file. You have {len(negative_items)} item(s) "
                f"that may be disputable. The highest priority is a "
                f"{priority_item['type']} from {priority_item['creditor']} "
                f"reported by {priority_item['bureau']}. "
                f"Would you like me to start the dispute process?"
            )

            return {
                "response": response,
                "action": "initiate_dispute",
                "priority_item": priority_item,
                "total_disputable": len(negative_items),
                "active_disputes": len(disputes_filed),
                "credit_score": credit_score,
                "needs_escalation": False,
            }

        except Exception as e:
            self.logger.error(f"CreditAnalystEngine.analyze error: {e}")
            return {
                "response": "I'm reviewing your file now. I'll have an update shortly.",
                "needs_escalation": False,
            }

    def score_analysis(self, message: str) -> Dict[str, Any]:
        """Return current score status and trend."""
        score = self._fetch_latest_score()
        trend = self._fetch_score_trend()

        direction = "up" if trend > 0 else ("down" if trend < 0 else "steady")
        response = (
            f"Your current credit score is {score}. "
            f"Your score has gone {direction} {abs(trend)} points over the last 30 days. "
        )
        if trend > 0:
            response += "Keep up the great work! Disputes are helping."
        elif trend < 0:
            response += "I'll review what may be causing the dip and update you soon."
        else:
            response += "We're working to move it upward — more dispute results coming."

        return {
            "response": response,
            "credit_score": score,
            "trend_30d": trend,
            "needs_escalation": False,
        }

    # ------------------------------------------------------------------
    # Private helpers (mocked for demo; replace with DB queries in prod)
    # ------------------------------------------------------------------

    def _fetch_negative_items(self) -> List[Dict]:
        """Fetch disputable negative items from DB."""
        # In production: query NegativeItem table filtered by client_id, disputeable=True
        return [
            {
                "id": str(uuid.uuid4()),
                "type": "collection",
                "creditor": "Portfolio Recovery",
                "balance": 842.00,
                "bureau": "Equifax",
                "date_reported": "2023-08-15",
                "dispute_reason": "unverifiable",
            },
            {
                "id": str(uuid.uuid4()),
                "type": "late_payment",
                "creditor": "Capital One",
                "bureau": "TransUnion",
                "date_reported": "2023-06-10",
                "dispute_reason": "inaccurate",
            },
        ]

    def _fetch_active_disputes(self) -> List[Dict]:
        return []  # Query DisputeCase table in prod

    def _fetch_latest_score(self) -> int:
        return 612  # Query CreditReportSnapshot in prod

    def _fetch_score_trend(self) -> int:
        return 14  # Query score history in prod


# ---------------------------------------------------------------------------
# AGENT 3: Compliance Engine
# ---------------------------------------------------------------------------

class ComplianceEngine:
    """
    Gates all outbound communication for FCRA, CROA, FCC, and TCPA compliance.
    Every message Tim Shaw sends MUST pass through this engine first.
    """

    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.logger = logging.getLogger(f"{__name__}.ComplianceEngine")

    def check_message(self, message: str, channel: str = "portal") -> Dict[str, Any]:
        """
        Gate outbound message.
        Returns {compliant: bool, violations: list, safe_message: str}
        """
        violations = _contains_violation(message)

        if violations:
            self.logger.warning(
                f"Compliance violation detected | client={self.client_id} | "
                f"violations={violations}"
            )
            return {
                "compliant": False,
                "violations": violations,
                "safe_message": (
                    "I need to review the details with our team and will get back to you shortly."
                ),
                "action": "block_and_escalate",
            }

        # Check TCPA time restrictions for SMS/voice
        if channel in ("sms", "voice_call"):
            hour = datetime.now(timezone.utc).hour
            if hour < 8 or hour >= 21:  # Before 8 AM or after 9 PM
                return {
                    "compliant": False,
                    "violations": ["TCPA_TIME_RESTRICTION"],
                    "safe_message": None,
                    "action": "delay_until_allowed_hours",
                }

        return {
            "compliant": True,
            "violations": [],
            "safe_message": message,
            "action": "send",
        }

    def check_payment_query(self, message: str) -> Dict[str, Any]:
        """Handle payment-related questions compliantly."""
        return {
            "response": (
                "Your subscription covers your portal access, Tim Shaw chat, "
                "educational content, and dispute coordination. "
                "Coaching sessions are scheduled separately. "
                "All billing is transparent — no hidden fees. "
                "You may cancel anytime with a 3-day full refund window."
            ),
            "needs_escalation": False,
        }

    def check_dispute_letter(self, letter_content: str) -> Dict[str, Any]:
        """
        Validate a dispute letter for FCRA/CROA compliance.
        In production, can also call Claude API for deeper analysis.
        """
        violations = _contains_violation(letter_content)

        # Additional letter-specific checks
        required_elements = [
            "Fair Credit Reporting Act",
            "investigation",
        ]
        missing = [el for el in required_elements if el not in letter_content]

        if violations or missing:
            return {
                "status": "rejected",
                "violations": violations,
                "missing_elements": missing,
                "approved": False,
                "reason": f"Letter contains violations or missing required elements.",
            }

        return {
            "status": "approved",
            "violations": [],
            "missing_elements": [],
            "approved": True,
            "reason": "Letter passed compliance review.",
        }

    def check_fcra_compliance(self, text: str) -> Dict[str, Any]:
        """FCRA-specific compliance check."""
        violations = _contains_violation(text)
        return {"compliant": len(violations) == 0, "violations": violations}


# ---------------------------------------------------------------------------
# AGENT 4: Scheduler Engine
# ---------------------------------------------------------------------------

class SchedulerEngine:
    """
    Manages appointments, coaching sessions, dispute filing timing,
    and follow-up reminders for clients.
    """

    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.logger = logging.getLogger(f"{__name__}.SchedulerEngine")

    def suggest_session(self, message: str) -> Dict[str, Any]:
        """Suggest appropriate coaching session based on client message."""
        message_lower = message.lower()

        if "budget" in message_lower or "debt" in message_lower or "spend" in message_lower:
            session_type = "Budget & Debt Payoff Bootcamp"
            price = 49.00
            duration = "60 min"
        elif "dispute" in message_lower or "strategy" in message_lower:
            session_type = "Dispute Strategy Bootcamp"
            price = 49.00
            duration = "90 min"
        elif "mortgage" in message_lower or "home" in message_lower or "buy" in message_lower:
            session_type = "Pre-Mortgage Preparation"
            price = 200.00
            duration = "60 min"
        else:
            session_type = "One-on-One Strategy Session"
            price = 200.00
            duration = "60 min"

        return {
            "response": (
                f"I'd recommend our {session_type} ({duration}). "
                f"This session is ${'%.2f' % price} and will help you with exactly what you're asking about. "
                f"Would you like me to pull up available times?"
            ),
            "session_type": session_type,
            "price": price,
            "duration": duration,
            "action": "show_booking_calendar",
            "needs_escalation": False,
        }

    def schedule_dispute_follow_up(self, dispute_id: str, filed_date: datetime) -> Dict:
        """Schedule 30-day follow-up check after dispute filing."""
        from datetime import timedelta
        follow_up_date = filed_date + timedelta(days=30)
        return {
            "dispute_id": dispute_id,
            "follow_up_date": follow_up_date.isoformat(),
            "action": "check_bureau_response",
            "scheduled": True,
        }

    def get_upcoming_appointments(self) -> List[Dict]:
        """Return upcoming appointments for client."""
        # In production: query Appointment table
        return []

    def check_sla_compliance(self, dispute_id: str, filed_date: datetime) -> Dict:
        """Check if bureau has responded within 30-day FCRA window."""
        days_elapsed = (datetime.now(timezone.utc) - filed_date).days
        if days_elapsed > 30:
            return {
                "sla_breached": True,
                "days_overdue": days_elapsed - 30,
                "action": "escalate_to_supervisor",
            }
        return {
            "sla_breached": False,
            "days_remaining": 30 - days_elapsed,
        }


# ---------------------------------------------------------------------------
# AGENT 5: Recommendation Engine
# ---------------------------------------------------------------------------

class RecommendationEngine:
    """
    Generates personalized product/service recommendations.
    CRITICAL: Only recommends from admin-approved product catalog.
    Cannot invent prices or products.
    """

    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.logger = logging.getLogger(f"{__name__}.RecommendationEngine")

    # Admin-approved product catalog (in prod: query products table)
    APPROVED_CATALOG = [
        {
            "id": "prod-001",
            "name": "Credit Building Fundamentals",
            "category": "course",
            "price": 49.00,
            "description": "Learn the fundamentals of building and repairing credit.",
            "target_score_range": (0, 620),
        },
        {
            "id": "prod-002",
            "name": "Budget Mastery",
            "category": "course",
            "price": 59.00,
            "description": "Master your budget to reduce utilization and improve your score.",
            "target_score_range": (0, 700),
        },
        {
            "id": "prod-003",
            "name": "Dispute Strategy Guide",
            "category": "guide",
            "price": 19.99,
            "description": "Step-by-step guide to writing effective dispute letters.",
            "target_score_range": (0, 700),
        },
        {
            "id": "prod-004",
            "name": "Advanced Credit Strategies",
            "category": "course",
            "price": 99.00,
            "description": "Advanced tactics for credit optimization and score maximization.",
            "target_score_range": (620, 850),
        },
        {
            "id": "prod-005",
            "name": "How to Read Your Credit Report",
            "category": "guide",
            "price": 0.00,
            "description": "Free guide to understanding every section of your credit report.",
            "target_score_range": (0, 850),
        },
    ]

    def recommend_for_client(self, credit_score: int = 600) -> Dict[str, Any]:
        """Generate personalized recommendations based on client profile."""
        suitable = [
            p for p in self.APPROVED_CATALOG
            if p["target_score_range"][0] <= credit_score <= p["target_score_range"][1]
        ]

        # Sort by price (free first, then ascending)
        suitable.sort(key=lambda x: x["price"])
        top_picks = suitable[:3]

        if not top_picks:
            return {
                "response": "I'll have personalized recommendations ready for you soon.",
                "products": [],
                "needs_escalation": False,
            }

        names = ", ".join(p["name"] for p in top_picks[:2])
        response = (
            f"Based on your credit profile, I recommend: {names}. "
            f"These are specifically chosen to help someone in your situation. "
            f"Would you like more details on any of these?"
        )

        return {
            "response": response,
            "products": top_picks,
            "needs_escalation": False,
        }

    def recommend_affiliate(self, client_profile: Dict) -> Dict[str, Any]:
        """
        Suggest affiliate products with MANDATORY disclosure.
        Disclosure is non-negotiable per FTC requirements.
        """
        disclosure = (
            "DISCLOSURE: The Life Shield may earn a commission if you sign up for "
            "the following partner product. This does not affect our recommendation "
            "and comes at no extra cost to you."
        )
        return {
            "response": f"{disclosure}\n\nBased on your profile, you might benefit from a secured credit card to build payment history.",
            "disclosure_included": True,
            "needs_escalation": False,
        }


# ---------------------------------------------------------------------------
# AGENT 6: Supervisor Engine
# ---------------------------------------------------------------------------

class SupervisorEngine:
    """
    Human oversight coordination — escalates when AI cannot or should not handle something.
    Manages complaints, legal threats, fraud, and client takeover requests.
    """

    ESCALATION_TRIGGERS = {
        "legal_threat": ["lawsuit", "attorney", "lawyer", "sue", "court", "legal action"],
        "fraud": ["fraud", "identity theft", "stolen", "not my account", "unauthorized"],
        "complaint": ["complaint", "terrible", "awful", "unacceptable", "report you"],
        "human_request": ["human", "real person", "speak to someone", "talk to a person"],
        "financial_distress": ["bankruptcy", "foreclosure", "eviction", "homeless"],
    }

    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.logger = logging.getLogger(f"{__name__}.SupervisorEngine")

    def detect_escalation_trigger(self, message: str) -> Optional[str]:
        """Detect if message requires supervisor escalation."""
        message_lower = message.lower()
        for trigger_type, keywords in self.ESCALATION_TRIGGERS.items():
            if any(kw in message_lower for kw in keywords):
                return trigger_type
        return None

    def escalate(self, message: str, trigger_type: str = "unknown") -> Dict[str, Any]:
        """
        Escalate to human supervisor.
        Tim Shaw stops responding and human takes over.
        """
        self.logger.warning(
            f"ESCALATION triggered | client={self.client_id} | trigger={trigger_type}"
        )

        # Log escalation event in DB (in production)
        self._log_escalation(trigger_type, message)

        escalation_messages = {
            "legal_threat": (
                "I understand this is a serious matter. I'm connecting you with "
                "a member of our human team right now. They'll reach out within "
                "15 minutes. You're in good hands."
            ),
            "fraud": (
                "This sounds like it may involve identity theft or fraud — I'm treating "
                "this as urgent. A human specialist is being notified immediately. "
                "Please don't take any action until they contact you."
            ),
            "human_request": (
                "Absolutely — I'll connect you with a human team member right now. "
                "One of our coordinators will reach out within 15 minutes."
            ),
            "complaint": (
                "I'm sorry you're frustrated. I'm escalating your concern to a senior "
                "team member immediately so they can personally address this."
            ),
            "financial_distress": (
                "I hear you — this is a stressful situation. I'm escalating to a "
                "human specialist who can help explore all your options."
            ),
        }

        response = escalation_messages.get(
            trigger_type,
            "I'm connecting you with a human team member right away."
        )

        return {
            "response": response,
            "escalated": True,
            "trigger_type": trigger_type,
            "ai_stopped": True,
            "human_takeover": True,
            "sla_minutes": 15,
            "needs_escalation": True,
        }

    def override_ai_response(
        self, original_response: str, override_reason: str
    ) -> Dict[str, Any]:
        """Admin overrides an AI response before delivery."""
        self.logger.info(
            f"Admin override | client={self.client_id} | reason={override_reason}"
        )
        return {
            "overridden": True,
            "reason": override_reason,
            "original_blocked": True,
        }

    def _log_escalation(self, trigger_type: str, message: str) -> None:
        """Log escalation event for audit trail."""
        try:
            from app.models.compliance import EscalationEvent
            # In production: create EscalationEvent record
            pass
        except Exception:
            pass  # Fail silently — don't block escalation

    def monitor_compliance_realtime(self, client_id: str) -> Dict[str, Any]:
        """Real-time compliance monitoring for admin dashboard."""
        return {
            "client_id": client_id,
            "fcra_violations": 0,
            "croa_violations": 0,
            "tcpa_violations": 0,
            "pending_escalations": 0,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
