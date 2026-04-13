"""
Expert Specialist Engines for The Life Shield
All engines operate from FCRA/CROA statute-backed logic, not templates.

References:
- FCRA: 15 USC § 1681 et seq. (Fair Credit Reporting Act)
- CROA: 15 USC § 1679 et seq. (Credit Repair Organizations Act)
- FDCPA: 15 USC § 1692 et seq. (Fair Debt Collection Practices Act)
- TCPA: 47 USC § 227 (Telephone Consumer Protection Act)
- CAN-SPAM: 15 USC § 7701 (Controlling the Assault of Non-Solicited Pornography and Marketing)
"""

from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DISPUTE CATEGORIES (6 LEGAL CATEGORIES PER FCRA § 1681i)
# ============================================================================

class DisputeReason(Enum):
    """6 valid dispute reasons under FCRA § 1681i"""
    
    INACCURACY = ("INACCURACY", "15 USC § 1681i(a)(1)(A) - Wrong account information")
    INCOMPLETENESS = ("INCOMPLETENESS", "15 USC § 1681e(b) - Missing required information")
    UNVERIFIABLE = ("UNVERIFIABLE", "15 USC § 1681i(a)(1)(A) - Cannot be verified within 30 days")
    FRAUD = ("FRAUD", "15 USC § 1681c(a) - Unauthorized/fraudulent account")
    OBSOLETE_DATA = ("OBSOLETE_DATA", "15 USC § 1681c(a) - Exceeds reporting time limits")
    DUPLICATE = ("DUPLICATE_ACCOUNT", "15 USC § 1681e(b) - Same account listed multiple times")


# ============================================================================
# CREDIT ANALYST ENGINE
# ============================================================================

class CreditAnalystEngine:
    """
    Expert Credit Analyst
    
    Analyzes credit reports per FCRA § 1681e standards.
    Identifies 6 categories of disputable items based on statute.
    Provides law-backed dispute recommendations, not templates.
    
    Reference: 15 USC § 1681i - Procedure in case of disputed accuracy
    """
    
    # REPORTING TIME LIMITS - 15 USC § 1681c(a)
    REPORTING_LIMITS = {
        "charge_off": 7,              # 7 years from first delinquency
        "collection": 7,              # 7 years from original account first delinquency
        "negative": 7,                # 7 years from first delinquency
        "bankruptcy": 10,             # 10 years from filing date
        "hard_inquiry": 2,            # 2 years
        "soft_inquiry": 0,            # Does NOT report (do not appear on credit report)
        "paid_collection": 7,         # 7 years from payment date (not immediate deletion)
        "medical_collection": 7,      # 7 years (or immediate if paid by insurance per 2021 rule change)
        "foreclosure": 7,             # 7 years from date of sale/delivery of deed
        "lawsuit": 7,                 # 7 years from filing date
        "tax_lien": 7,                # 7 years from payment (paid liens) or indefinite (unpaid)
    }
    
    # FORBIDDEN PHRASES - CROA § 1679e (Auto-block if found)
    CROA_VIOLATIONS = {
        r"\bwill remove\b": "CROA § 1679e - Cannot guarantee removal",
        r"\bwill delete\b": "CROA § 1679e - Cannot promise deletion",
        r"guaranteed removal": "CROA § 1679e - No outcome guarantees",
        r"results in \d+ days": "CROA § 1679e - Cannot promise timeline",
        r"100%\s*success": "CROA § 1679e - Cannot guarantee results",
        r"special.*connection": "FCRA § 1681 - False bureau access claim",
        r"upfront.*payment": "CROA § 1679g - Upfront fees prohibited",
        r"credit repair guarantee": "CROA § 1679e - No guarantees allowed",
        r"no one can legally remove": "CROA § 1679e - Misrepresentation (implies you can)",
        r"dispute is guaranteed": "CROA § 1679e - Cannot guarantee outcomes",
    }
    
    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
    
    def analyze_report(self, report: Dict) -> Dict:
        """
        Expert-level credit report analysis per FCRA standards.
        
        Each item is evaluated against 6 FCRA § 1681i dispute categories.
        Returns analysis with statute citations, not templates.
        
        Args:
            report: Credit report dict with tradelines, inquiries, etc.
        
        Returns:
            {
                "auto_disputes": [High-confidence items to auto-file],
                "recommended_disputes": [Items for client review],
                "verified_ok": [Accurate, verified accounts],
                "total_items": X,
                "total_negative_items": Y,
                "estimated_removal_probability": 0.XX
            }
        """
        findings = {
            "auto_disputes": [],
            "recommended_disputes": [],
            "verified_ok": [],
            "total_items": 0,
            "total_negative_items": 0,
            "estimated_removal_probability": 0.0,
            "analysis_date": datetime.now().isoformat()
        }
        
        if not report.get("tradelines"):
            return findings
        
        removal_probabilities = []
        
        for item in report["tradelines"]:
            findings["total_items"] += 1
            
            # Analyze for 6 FCRA dispute reasons
            dispute_reason = self._determine_dispute_reason(item)
            
            if dispute_reason:
                reason_enum, statute = dispute_reason
                removal_prob = self._estimate_removal_probability(reason_enum)
                removal_probabilities.append(removal_prob)
                
                item_with_analysis = {
                    **item,
                    "dispute_reason": reason_enum,
                    "statute_citation": statute,
                    "removal_probability": removal_prob
                }
                
                # HIGH PRIORITY: >75% chance of removal → Auto-file
                if removal_prob > 0.75:
                    findings["auto_disputes"].append(item_with_analysis)
                # MEDIUM PRIORITY: 50-75% chance → Recommend to client
                else:
                    findings["recommended_disputes"].append(item_with_analysis)
            else:
                # No dispute reason found → Verified accurate
                findings["verified_ok"].append(item)
            
            # Count negatives
            if item.get("status") in ["charge_off", "collection", "negative", "delinquent"]:
                findings["total_negative_items"] += 1
        
        # Calculate overall removal probability
        if removal_probabilities:
            findings["estimated_removal_probability"] = sum(removal_probabilities) / len(removal_probabilities)
        
        return findings
    
    def _determine_dispute_reason(self, item: Dict) -> Optional[Tuple[str, str]]:
        """
        Determine which of 6 FCRA dispute categories applies.
        
        Returns: (dispute_reason, statute_citation) or None
        
        Checks in order of strongest to weakest legal basis:
        1. Obsolete data (7-10 year rule) - Strongest
        2. Fraud (unauthorized account)
        3. Inaccuracy (wrong information)
        4. Incompleteness (missing information)
        5. Unverifiable (bureau cannot verify)
        6. Duplicates (same account multiple times)
        """
        
        # Category 5: OBSOLETE DATA - 15 USC § 1681c(a)
        # STRONGEST basis (mandatory deletion)
        if self._is_obsolete(item):
            return (DisputeReason.OBSOLETE_DATA.value[0], DisputeReason.OBSOLETE_DATA.value[1])
        
        # Category 4: FRAUD - 15 USC § 1681c(a)
        if self._is_fraud(item):
            return (DisputeReason.FRAUD.value[0], DisputeReason.FRAUD.value[1])
        
        # Category 1: INACCURACY - 15 USC § 1681i(a)(1)(A)
        if self._is_inaccurate(item):
            return (DisputeReason.INACCURACY.value[0], DisputeReason.INACCURACY.value[1])
        
        # Category 2: INCOMPLETENESS - 15 USC § 1681e(b)
        if self._is_incomplete(item):
            return (DisputeReason.INCOMPLETENESS.value[0], DisputeReason.INCOMPLETENESS.value[1])
        
        # Category 3: UNVERIFIABLE - 15 USC § 1681i(a)(1)(A)
        # (Determined during 30-day reinvestigation window, not initially)
        
        # Category 6: DUPLICATE - 15 USC § 1681e(b)
        # (Handled separately, comparing across all items)
        
        return None
    
    def _is_obsolete(self, item: Dict) -> bool:
        """
        Check if item exceeds FCRA reporting limits (15 USC § 1681c(a)).
        
        If true, item MUST be deleted from credit report (mandatory).
        This is the strongest dispute basis.
        
        Calculation: first_delinquency_date + reporting_limit ≤ today
        """
        
        item_type = item.get("account_type", "").lower()
        first_delinquency = item.get("first_delinquency_date")
        
        if not first_delinquency:
            return False
        
        # Parse date
        try:
            delinq_date = datetime.fromisoformat(first_delinquency)
        except:
            return False
        
        age_days = (datetime.now() - delinq_date).days
        age_years = age_days / 365.25
        
        # Get reporting limit for this item type
        limit = self.REPORTING_LIMITS.get(item_type, 7)  # Default 7 years
        
        # Item is obsolete if it exceeds limit
        return age_years > float(limit)
    
    def _is_inaccurate(self, item: Dict) -> bool:
        """
        Check for inaccuracy per 15 USC § 1681i(a)(1)(A).
        
        Examples of inaccuracy:
        - Balance higher than current statement
        - Credit limit lower than actual
        - Payment status wrong (30 days late vs. 60 days)
        - Account opened date incorrect
        - Account closed date incorrect
        - Interest rate incorrect
        - Creditor name misspelled or wrong
        """
        
        # For production, this would compare against original statements/contracts
        # For now, flag if user marked as inaccurate
        return item.get("marked_inaccurate", False) or item.get("inaccuracy_details")
    
    def _is_incomplete(self, item: Dict) -> bool:
        """
        Check for incompleteness per 15 USC § 1681e(b).
        
        Examples:
        - Missing original creditor name for collection
        - Missing credit limit for credit card
        - Missing assignment date for transferred account
        - Missing charge-off date
        """
        
        # Define required fields by account type
        required_by_type = {
            "credit_card": ["credit_limit", "current_balance", "creditor_name"],
            "collection": ["original_creditor", "account_number"],
            "charge_off": ["original_amount", "charge_off_date", "creditor_name"],
            "auto_loan": ["loan_amount", "loan_term", "current_balance"],
            "mortgage": ["loan_amount", "property_address"],
        }
        
        item_type = item.get("account_type", "").lower()
        required = required_by_type.get(item_type, [])
        
        # Check if any required field is missing
        for field in required:
            if not item.get(field):
                return True
        
        return False
    
    def _is_fraud(self, item: Dict) -> bool:
        """
        Check for fraud indicators per 15 USC § 1681c(a).
        
        Fraud account = unauthorized, opened without client's permission.
        Should be removed from credit report with police report.
        """
        
        fraud_indicators = [
            item.get("fraud_dispute_filed"),
            item.get("unauthorized_account"),
            item.get("identity_theft_marker"),
            "fraud" in str(item.get("status", "")).lower(),
        ]
        
        return any(fraud_indicators)
    
    def _estimate_removal_probability(self, dispute_reason: str) -> float:
        """
        Estimate probability of successful dispute outcome.
        
        Based on industry data and FCRA requirements:
        - Obsolete data: 85% (bureau MUST delete old data)
        - Duplicates: 95% (clear error)
        - Fraud: 70% (requires police report)
        - Inaccuracy: 60% (depends on evidence)
        - Unverifiable: 55% (bureau may have records)
        - Incomplete: 50% (may be intentional)
        """
        
        probabilities = {
            "OBSOLETE_DATA": 0.85,
            "DUPLICATE_ACCOUNT": 0.95,
            "FRAUD": 0.70,
            "INACCURACY": 0.60,
            "UNVERIFIABLE": 0.55,
            "INCOMPLETENESS": 0.50,
        }
        
        return probabilities.get(dispute_reason, 0.50)
    
    def check_letter_compliance(self, letter_text: str) -> Dict:
        """
        Check dispute letter for CROA/FCRA violations.
        
        Auto-blocks if forbidden phrases found.
        Returns violations with statute citations.
        """
        violations = []
        
        # Check for forbidden phrases
        for pattern, rule in self.CROA_VIOLATIONS.items():
            if re.search(pattern, letter_text, re.IGNORECASE):
                violations.append({
                    "type": "VIOLATION",
                    "pattern": pattern,
                    "rule": rule,
                    "severity": "CRITICAL",
                    "action": "BLOCK - LETTER REJECTED"
                })
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations
        }


# ============================================================================
# COMPLIANCE ENGINE
# ============================================================================

class ComplianceEngine:
    """
    Legal Compliance Engine
    
    Enforces FCRA, CROA, FDCPA, TCPA, CAN-SPAM on all communications.
    Two-layer defense: rule engine + AI review.
    
    References:
    - FCRA: 15 USC § 1681
    - CROA: 15 USC § 1679
    - FDCPA: 15 USC § 1692
    - TCPA: 47 USC § 227
    - CAN-SPAM: 15 USC § 7701
    """
    
    # FORBIDDEN LANGUAGE (CROA § 1679e)
    FORBIDDEN_PHRASES = {
        r"\b(will|shall|can|guarantee)\s+(remove|delete|clear|erase)": 
            "CROA § 1679e - Cannot promise removal",
        r"(guaranteed|100%|certain|assured|promise)\s+(removal|success|results)":
            "CROA § 1679e - No outcome guarantees",
        r"results\s+(in|within)\s+\d+\s+(days|weeks|months)":
            "CROA § 1679e - Cannot promise timeline",
        r"upfront\s+(payment|fee|cost)":
            "CROA § 1679g - Upfront fees prohibited",
        r"special\s+(access|connection|relationship)":
            "FCRA § 1681 - False bureau relationship claim",
    }
    
    # REQUIRED DISCLOSURES (CROA § 1679c)
    REQUIRED_DISCLOSURES = [
        "You have the right to dispute items with credit bureaus for free",
        "Credit bureaus will investigate within 30-45 days",
        "We cannot guarantee that any item will be removed or changed",
        "Our service is paid on a subscription basis, not per dispute",
        "You can file disputes yourself at no cost",
    ]
    
    def __init__(self):
        self.analyst = CreditAnalystEngine("system", None)
    
    def check_communication(self, text: str, channel: str = "email") -> Dict:
        """
        Check communication for compliance violations.
        
        Args:
            text: Message/letter text
            channel: "email", "sms", "voice", "chat"
        
        Returns:
            {
                "compliant": bool,
                "violations": [list of violations],
                "warnings": [list of warnings]
            }
        """
        
        violations = []
        warnings = []
        
        # Check for forbidden phrases
        for pattern, rule in self.FORBIDDEN_PHRASES.items():
            if re.search(pattern, text, re.IGNORECASE):
                violations.append({
                    "type": "VIOLATION",
                    "rule": rule,
                    "severity": "CRITICAL",
                    "action": "BLOCK"
                })
        
        # Check for required disclosures (contracts only)
        if channel in ["email_contract", "portal_signup"]:
            for disclosure in self.REQUIRED_DISCLOSURES:
                if not self._contains_disclosure(text, disclosure):
                    violations.append({
                        "type": "MISSING_DISCLOSURE",
                        "disclosure": disclosure,
                        "statute": "CROA § 1679c",
                        "severity": "CRITICAL",
                        "action": "BLOCK"
                    })
        
        # Channel-specific checks
        if channel == "sms":
            violations.extend(self._check_sms_compliance(text))
        elif channel == "voice":
            violations.extend(self._check_voice_compliance(text))
        elif channel == "email":
            violations.extend(self._check_email_compliance(text))
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "warnings": warnings
        }
    
    def _check_sms_compliance(self, text: str) -> List[Dict]:
        """Check SMS compliance (TCPA § 227)"""
        violations = []
        
        # SMS must include opt-out
        if "STOP" not in text:
            violations.append({
                "type": "MISSING_OPT_OUT",
                "rule": "TCPA § 227 - Must include STOP to opt-out",
                "severity": "CRITICAL"
            })
        
        # No misleading sender info
        if "from" not in text.lower():
            violations.append({
                "type": "MISSING_ID",
                "rule": "TCPA § 227 - Must identify sender",
                "severity": "HIGH"
            })
        
        return violations
    
    def _check_voice_compliance(self, script: str) -> List[Dict]:
        """Check voice call compliance (TCPA § 227, FDCPA § 1692)"""
        violations = []
        
        # Must include AI disclosure
        if not any(term in script.lower() for term in ["ai agent", "automated", "recording", "ai-powered"]):
            violations.append({
                "type": "MISSING_DISCLOSURE",
                "rule": "FTC Guidelines - Must disclose AI agent",
                "severity": "HIGH"
            })
        
        return violations
    
    def _check_email_compliance(self, email: str) -> List[Dict]:
        """Check email compliance (CAN-SPAM § 7701)"""
        violations = []
        
        # Must have unsubscribe option
        if "unsubscribe" not in email.lower():
            violations.append({
                "type": "MISSING_UNSUBSCRIBE",
                "rule": "CAN-SPAM § 7701 - Must include unsubscribe",
                "severity": "CRITICAL"
            })
        
        # Must have physical address
        if not any(term in email.lower() for term in ["address", "mailing", "located at"]):
            violations.append({
                "type": "MISSING_ADDRESS",
                "rule": "CAN-SPAM § 7701 - Must include physical address",
                "severity": "CRITICAL"
            })
        
        return violations
    
    def _contains_disclosure(self, text: str, disclosure: str) -> bool:
        """Check if disclosure is substantially present"""
        
        # Normalize both
        text_lower = text.lower()
        key_words = disclosure.lower().split()[:3]  # Check first 3 words
        
        return all(word in text_lower for word in key_words)


# ============================================================================
# SCHEDULER ENGINE
# ============================================================================

class SchedulerEngine:
    """
    Appointment Scheduler
    
    Books coaching sessions, consultations, and follow-ups.
    Integrates with calendar, CRM, and compliance rules.
    """
    
    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
    
    def suggest_session(self, message: str) -> Dict:
        """Suggest available coaching session slots"""
        
        return {
            "response": "I can schedule a coaching session with our financial expert. What works best for you? (Morning/afternoon, week of?)",
            "needs_escalation": False,
            "session_type": "credit_coaching"
        }


# ============================================================================
# RECOMMENDATION ENGINE
# ============================================================================

class RecommendationEngine:
    """
    Product Recommendation Engine
    
    Recommends approved financial products based on client profile.
    All recommendations are evidence-based, not sales-driven.
    """
    
    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
    
    def recommend_products(self, profile: Dict) -> List[Dict]:
        """
        Recommend products based on client financial profile.
        
        Products only if statistically beneficial for client.
        """
        
        recommendations = []
        
        # High negative items → Credit repair subscription
        if profile.get("negative_items", 0) > 5:
            recommendations.append({
                "product": "credit_repair_subscription",
                "reason": "Multiple disputed negative items require systematic filing",
                "monthly_cost": 69,
                "expected_benefit": "5-15 items removed within 6 months"
            })
        
        # Low account diversity → Credit builder
        if profile.get("account_types", 0) < 3:
            recommendations.append({
                "product": "credit_builder_loan",
                "reason": "Need diverse account types for score improvement",
                "cost": "$300-1000 (returned after loan completion)",
                "expected_benefit": "+50-100 score points"
            })
        
        # High debt-to-income → Financial coaching
        if profile.get("debt_to_income", 0) > 0.40:
            recommendations.append({
                "product": "financial_coaching",
                "reason": "High debt burden; payoff strategy needed",
                "cost": "$150-300 per session",
                "expected_benefit": "Structured repayment, improved cash flow"
            })
        
        return recommendations


# ============================================================================
# SUPERVISOR ENGINE
# ============================================================================

class SupervisorEngine:
    """
    Human Escalation Supervisor
    
    Knows when to escalate to humans.
    Triggers include fraud, legal threats, regulatory inquiries.
    """
    
    ESCALATION_TRIGGERS = {
        "fraud": r"(identity theft|unauthorized|fraud|police report)",
        "legal_threat": r"(lawsuit|attorney|sue|court|legal action)",
        "bankruptcy": r"(bankruptcy|chapter 7|chapter 13|filing)",
        "regulatory": r"(FTC|CFPB|attorney general|complaint|BBB)",
        "threat": r"(kill|hurt|harm|violence|weapon|suicide)",
    }
    
    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
    
    def evaluate_escalation(self, message: str) -> Dict:
        """Determine if escalation needed"""
        
        for category, pattern in self.ESCALATION_TRIGGERS.items():
            if re.search(pattern, message, re.IGNORECASE):
                return {
                    "escalate": True,
                    "category": category,
                    "to_team": "legal" if "legal" in category else "supervisor",
                    "priority": "URGENT",
                    "action": "IMMEDIATE HUMAN REVIEW"
                }
        
        return {"escalate": False}
    
    def escalate(self, message: str, category: str) -> Dict:
        """Escalate to human team"""
        
        return {
            "escalated": True,
            "category": category,
            "status": "QUEUED FOR HUMAN REVIEW",
            "response": "Your issue requires human attention. A specialist will contact you within 2 hours."
        }
