"""
Compliance Check Service

Standalone compliance engine for outbound communications, dispute letters,
and recommendations. This is separate from Claude-based letter compliance —
this service handles rule-based checks and can be called synchronously.

Covers:
- FCRA (Fair Credit Reporting Act) language rules
- CROA (Credit Repair Organizations Act) prohibited promises
- FCC/TCPA communication timing & consent
- Promise/guarantee detection
- Identity misrepresentation detection
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class ComplianceSeverity(str, Enum):
    BLOCK = "block"       # Hard block — must not proceed
    WARN = "warn"         # Soft warn — proceed with caution / human review
    INFO = "info"         # Informational


@dataclass
class ComplianceViolation:
    rule: str
    severity: ComplianceSeverity
    description: str
    matched_text: Optional[str] = None


@dataclass
class ComplianceCheckResult:
    passed: bool                              # True if no BLOCK violations
    violations: list[ComplianceViolation] = field(default_factory=list)
    warnings: list[ComplianceViolation] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_blocks(self) -> bool:
        return any(v.severity == ComplianceSeverity.BLOCK for v in self.violations)

    @property
    def flag_list(self) -> list[str]:
        return [v.rule for v in self.violations + self.warnings]


# ---------------------------------------------------------------------------
# Prohibited patterns (CROA/FCRA)
# ---------------------------------------------------------------------------

# Patterns that BLOCK sending/filing (hard violations)
_BLOCK_PATTERNS = [
    # Outcome guarantees — stem-match without strict trailing boundary
    (
        r"\b(guarantee[sd]?|guaranteed)\b.{0,50}(remov|delet|wipe|erase|improv|increas)",
        "croa.outcome_guarantee",
        "CROA § 4: Promise of credit repair outcome (removal, deletion, score increase) is prohibited.",
    ),
    (
        r"\b(your score (will|shall|must) (go up|increase|improve|rise))",
        "croa.score_promise",
        "CROA § 4: Direct score improvement promise is prohibited.",
    ),
    (
        r"(100%\s*(guaranteed|promise|certain|sure))",
        "croa.certainty_claim",
        "CROA § 4: Certainty claims about credit repair outcomes are prohibited.",
    ),
    # Identity fraud
    (
        r"\b(create|establish|build|obtain).{0,20}(new|alternate|second|different).{0,20}(credit identity|credit file|ssn|ein|cpn|credit profile)",
        "fcra.identity_fraud",
        "FCRA: Advising clients to create a new credit identity is illegal.",
    ),
    (
        r"\b(cpn|credit privacy number|credit profile number)\b",
        "fcra.cpn_fraud",
        "FCRA: Credit Privacy Numbers (CPNs) are fraudulent. Do not reference.",
    ),
    # Fabricated disputes
    (
        r"\b(make up|fabricate|invent|lie about|falsely claim)\b",
        "fcra.fabrication",
        "FCRA § 623: Filing false disputes is a federal violation.",
    ),
    # Harassment
    (
        r"\b(sue you|take legal action|file a complaint against you|report you to)\b.{0,30}\b(immediately|right now|today)\b",
        "compliance.harassment",
        "Threatening language in dispute letters is prohibited and counterproductive.",
    ),
    # Upfront payment promises
    (
        r"\b(pay.{0,20}(before|upfront|in advance).{0,20}(we|our|the).{0,20}(file|dispute|remove|fix))\b",
        "croa.upfront_payment",
        "CROA § 5: Charging upfront before services are performed is prohibited.",
    ),
]

# Patterns that WARN (soft flags — require human review)
_WARN_PATTERNS = [
    (
        r"\b(may|might|could|should|expect|likely)\b.{0,30}\b(improve|increase|go up|boost)\b.{0,30}\b(score|points)\b",
        "croa.soft_score_suggestion",
        "Soft score improvement suggestion — ensure no guarantee is implied.",
    ),
    (
        r"\b(definitely|certainly|absolutely|without doubt)\b",
        "compliance.certainty_language",
        "Certainty language may imply guarantees — review context.",
    ),
    (
        r"\b(bankruptcy|chapter 7|chapter 13)\b",
        "compliance.bankruptcy_mention",
        "Bankruptcy mention — ensure advice is appropriate and not legal counsel.",
    ),
    (
        r"\b(attorney|lawyer|legal counsel|law firm)\b",
        "compliance.legal_reference",
        "Legal reference — ensure this is appropriate context and properly disclosed.",
    ),
    (
        r"\b(ssn|social security number|date of birth|dob|full account number)\b",
        "compliance.pii_in_message",
        "Potential PII in outbound message — verify this is necessary and encrypted in transit.",
    ),
]


# ---------------------------------------------------------------------------
# Communication compliance
# ---------------------------------------------------------------------------

def check_communication_compliance(
    content: str,
    channel: str,
    client_has_sms_consent: bool = False,
    client_has_email_consent: bool = False,
    client_has_call_consent: bool = False,
    client_on_dnc: bool = False,
    current_hour: Optional[int] = None,
) -> ComplianceCheckResult:
    """
    Check a communication for compliance before sending.

    Args:
        content: The message content
        channel: sms | email | voice | chat
        client_has_*_consent: Consent flags
        client_on_dnc: Whether client is on Do-Not-Call list
        current_hour: Hour of day (0-23) for timing checks

    Returns:
        ComplianceCheckResult
    """
    violations: list[ComplianceViolation] = []
    warnings: list[ComplianceViolation] = []

    # Channel consent checks
    if channel == "sms" and not client_has_sms_consent:
        violations.append(ComplianceViolation(
            rule="tcpa.no_sms_consent",
            severity=ComplianceSeverity.BLOCK,
            description="TCPA: Client has not consented to SMS communication.",
        ))

    if channel == "email" and not client_has_email_consent:
        violations.append(ComplianceViolation(
            rule="can_spam.no_email_consent",
            severity=ComplianceSeverity.BLOCK,
            description="CAN-SPAM: Client has not consented to email communication.",
        ))

    if channel == "voice" and not client_has_call_consent:
        violations.append(ComplianceViolation(
            rule="tcpa.no_call_consent",
            severity=ComplianceSeverity.BLOCK,
            description="TCPA: Client has not consented to voice calls.",
        ))

    if channel == "voice" and client_on_dnc:
        violations.append(ComplianceViolation(
            rule="tcpa.dnc_list",
            severity=ComplianceSeverity.BLOCK,
            description="TCPA/FCC: Client is on Do-Not-Call list.",
        ))

    # Timing checks (8 AM – 9 PM)
    if current_hour is not None and channel in ("sms", "voice"):
        if current_hour < 8 or current_hour >= 21:
            violations.append(ComplianceViolation(
                rule="tcpa.outside_hours",
                severity=ComplianceSeverity.BLOCK,
                description=f"TCPA: Outbound {channel} outside permitted hours (8 AM–9 PM). Current hour: {current_hour}.",
            ))

    # Content checks
    content_result = check_content_compliance(content)
    violations.extend(content_result.violations)
    warnings.extend(content_result.warnings)

    passed = not any(v.severity == ComplianceSeverity.BLOCK for v in violations)
    return ComplianceCheckResult(passed=passed, violations=violations, warnings=warnings)


# ---------------------------------------------------------------------------
# Content compliance check (letter or message)
# ---------------------------------------------------------------------------

def check_content_compliance(content: str) -> ComplianceCheckResult:
    """
    Run rule-based FCRA/CROA compliance checks on text content.

    Works on dispute letters, SMS messages, email bodies — any text.
    """
    violations: list[ComplianceViolation] = []
    warnings: list[ComplianceViolation] = []

    content_lower = content.lower()

    for pattern, rule_id, description in _BLOCK_PATTERNS:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            violations.append(ComplianceViolation(
                rule=rule_id,
                severity=ComplianceSeverity.BLOCK,
                description=description,
                matched_text=match.group(0),
            ))
            logger.warning(
                "Compliance BLOCK violation found: rule=%s matched=%s",
                rule_id, match.group(0),
            )

    for pattern, rule_id, description in _WARN_PATTERNS:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            warnings.append(ComplianceViolation(
                rule=rule_id,
                severity=ComplianceSeverity.WARN,
                description=description,
                matched_text=match.group(0),
            ))

    passed = len(violations) == 0
    return ComplianceCheckResult(passed=passed, violations=violations, warnings=warnings)


# ---------------------------------------------------------------------------
# Dispute letter specific check
# ---------------------------------------------------------------------------

def check_dispute_letter_compliance(letter_content: str) -> ComplianceCheckResult:
    """
    Specialized compliance check for dispute letters.
    Adds letter-specific FCRA rules on top of general content checks.
    """
    result = check_content_compliance(letter_content)

    # Additional letter-specific checks
    if len(letter_content.strip()) < 100:
        result.violations.append(ComplianceViolation(
            rule="fcra.letter_too_short",
            severity=ComplianceSeverity.BLOCK,
            description="Dispute letter is too short to constitute a valid dispute.",
        ))

    # Check for required elements
    if "fcra" not in letter_content.lower() and "fair credit" not in letter_content.lower():
        result.warnings.append(ComplianceViolation(
            rule="fcra.no_statute_reference",
            severity=ComplianceSeverity.WARN,
            description="Letter does not reference FCRA — recommend adding legal citation.",
        ))

    # Re-evaluate passed based on all violations
    result.passed = not result.has_blocks
    return result
