"""
Dispute Letter Generation Service

Uses OpenAI for content generation + Claude for compliance checking.
Generates FCRA-compliant dispute letters tailored to each case.

Flow:
  1. Collect client/tradeline context
  2. OpenAI drafts the letter
  3. Claude performs compliance review
  4. Return draft with compliance verdict + flags
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LetterContext:
    """All facts needed to generate a dispute letter."""
    client_full_name: str
    client_address_line1: str
    client_city: str
    client_state: str
    client_zip_code: str
    client_ssn_last4: str
    creditor_name: str
    account_number_masked: str
    dispute_reason: str          # DisputeReason enum value (string)
    item_description: str        # Human-readable description of the item
    bureau: str                  # equifax | experian | transunion
    analyst_notes: Optional[str] = None


@dataclass
class ComplianceResult:
    """Result of Claude compliance review."""
    passed: bool
    flags: list[str] = field(default_factory=list)
    explanation: str = ""
    checked_by_model: str = ""


@dataclass
class GeneratedLetter:
    """Full result returned by generate_dispute_letter()."""
    content: str
    ai_model_used: str
    generation_prompt_hash: str
    compliance: ComplianceResult


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

GENERATION_SYSTEM_PROMPT = """You are a professional credit dispute specialist with 20 years of experience filing FCRA-compliant dispute letters.

Your letters:
- Are professional, firm, and factual
- Reference FCRA Section 611 (right to dispute)
- Do NOT make income promises, outcome guarantees, or score predictions
- Do NOT make false statements or fraudulent claims
- Are addressed correctly to the specified credit bureau
- Include the client's identifying information
- Clearly identify the disputed item
- State the specific reason for the dispute
- Request investigation and removal/correction
- Are concise (300–500 words maximum)

Write in plain English. Do not use aggressive or threatening language.
"""

COMPLIANCE_SYSTEM_PROMPT = """You are a FCRA/CROA compliance officer reviewing credit dispute letters before they are filed.

Your job: identify any language that violates the Fair Credit Reporting Act (FCRA) or the Credit Repair Organizations Act (CROA).

RED FLAGS to check for:
1. False statements (fabricated facts, made-up disputes)
2. Threats or aggressive language toward the bureau
3. Promises of score improvements ("Your score will go up 100 points")
4. Outcome guarantees ("This item WILL be removed")
5. Frivolous disputes (no factual basis stated)
6. Pressure tactics or harassment
7. Statements suggesting illegal activity
8. Requests to remove accurate, verifiable information without legal basis
9. Misleading identity claims
10. Any language that could expose the company to regulatory liability

Respond ONLY with valid JSON:
{
  "passed": true/false,
  "flags": ["list of specific flags found, or empty list if passed"],
  "explanation": "Brief explanation of your finding"
}
"""


# ---------------------------------------------------------------------------
# Bureau addresses
# ---------------------------------------------------------------------------

BUREAU_ADDRESSES = {
    "equifax": "Equifax Information Services LLC\nP.O. Box 740256\nAtlanta, GA 30374-0256",
    "experian": "Experian\nP.O. Box 4500\nAllen, TX 75013",
    "transunion": "TransUnion LLC\nConsumer Dispute Center\nP.O. Box 2000\nChester, PA 19016",
}

DISPUTE_REASON_NARRATIVES = {
    "inaccurate": "contains inaccurate information that does not correctly reflect my credit history",
    "incomplete": "is incomplete and fails to accurately represent the account status",
    "unverifiable": "cannot be verified and should therefore be removed pursuant to FCRA § 611",
    "obsolete": "is obsolete and has exceeded the 7-year reporting period under FCRA § 605",
    "fraudulent": "is fraudulent and was opened without my knowledge or consent as a result of identity theft",
    "not_mine": "does not belong to me and was incorrectly associated with my credit file",
    "wrong_balance": "reflects an incorrect balance that does not match my records",
    "wrong_status": "reports an incorrect account status that misrepresents the true standing of this account",
    "duplicate": "is a duplicate entry already reported elsewhere in my credit file",
}


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------

async def generate_dispute_letter(ctx: LetterContext) -> GeneratedLetter:
    """
    Generate a dispute letter using OpenAI, then validate with Claude.

    Returns a GeneratedLetter with content + compliance result.
    Falls back to a template-based letter if AI APIs are unavailable.
    """
    reason_narrative = DISPUTE_REASON_NARRATIVES.get(
        ctx.dispute_reason,
        "contains information I believe to be inaccurate"
    )
    bureau_address = BUREAU_ADDRESSES.get(ctx.bureau.lower(), "Credit Bureau")

    # Build the user prompt
    user_prompt = f"""Generate a professional FCRA dispute letter with these details:

CLIENT INFORMATION:
- Full Name: {ctx.client_full_name}
- Address: {ctx.client_address_line1}, {ctx.client_city}, {ctx.client_state} {ctx.client_zip_code}
- SSN (last 4): {ctx.client_ssn_last4}

BUREAU:
{bureau_address}

DISPUTED ITEM:
- Creditor/Account: {ctx.creditor_name}
- Account Number: {ctx.account_number_masked}
- Dispute Reason: This item {reason_narrative}
- Item Description: {ctx.item_description}
{"- Analyst Notes: " + ctx.analyst_notes if ctx.analyst_notes else ""}

Write the complete letter, properly formatted, including date, addresses, subject line, body, and closing.
"""

    prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()

    # Attempt OpenAI generation
    letter_content, model_used = await _generate_with_openai(
        user_prompt, GENERATION_SYSTEM_PROMPT
    )

    if not letter_content:
        # Fallback: build template letter
        logger.warning("OpenAI unavailable — using template letter fallback")
        letter_content = _build_template_letter(ctx, reason_narrative, bureau_address)
        model_used = "template_fallback"

    # Compliance check via Claude
    compliance = await _check_compliance_with_claude(letter_content)

    return GeneratedLetter(
        content=letter_content,
        ai_model_used=model_used,
        generation_prompt_hash=prompt_hash,
        compliance=compliance,
    )


# ---------------------------------------------------------------------------
# OpenAI generation
# ---------------------------------------------------------------------------

async def _generate_with_openai(user_prompt: str, system_prompt: str) -> tuple[str, str]:
    """Call OpenAI chat completions. Returns (content, model_name) or ("", "")."""
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not configured — skipping OpenAI generation")
        return "", ""

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            model = data.get("model", settings.OPENAI_MODEL)
            return content, model

    except Exception as exc:
        logger.error("OpenAI letter generation failed", exc_info=exc)
        return "", ""


# ---------------------------------------------------------------------------
# Claude compliance check
# ---------------------------------------------------------------------------

async def _check_compliance_with_claude(letter_content: str) -> ComplianceResult:
    """Use Claude to perform compliance review of the generated letter."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured — skipping Claude compliance check")
        return ComplianceResult(
            passed=True,
            flags=[],
            explanation="Compliance check skipped — API key not configured. Manual review required.",
            checked_by_model="none",
        )

    try:
        import httpx

        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 500,
            "system": COMPLIANCE_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": f"Review this dispute letter for compliance:\n\n{letter_content}",
                }
            ],
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_text = data["content"][0]["text"].strip()

            # Parse JSON response
            compliance_data = json.loads(raw_text)
            return ComplianceResult(
                passed=bool(compliance_data.get("passed", False)),
                flags=compliance_data.get("flags", []),
                explanation=compliance_data.get("explanation", ""),
                checked_by_model=settings.ANTHROPIC_MODEL,
            )

    except json.JSONDecodeError as exc:
        logger.error("Claude returned non-JSON compliance response", exc_info=exc)
        return ComplianceResult(
            passed=False,
            flags=["compliance_parse_error"],
            explanation="Compliance check returned unparseable response. Manual review required.",
            checked_by_model=settings.ANTHROPIC_MODEL,
        )
    except Exception as exc:
        logger.error("Claude compliance check failed", exc_info=exc)
        return ComplianceResult(
            passed=False,
            flags=["compliance_check_error"],
            explanation=f"Compliance check failed with error. Manual review required.",
            checked_by_model="error",
        )


# ---------------------------------------------------------------------------
# Template fallback letter
# ---------------------------------------------------------------------------

def _build_template_letter(ctx: LetterContext, reason_narrative: str, bureau_address: str) -> str:
    """Build a standards-compliant template letter when AI is unavailable."""
    from datetime import date
    today = date.today().strftime("%B %d, %Y")

    return f"""{today}

{bureau_address}

Re: Formal Dispute of Credit Report Item — {ctx.creditor_name} | Account: {ctx.account_number_masked}

To Whom It May Concern:

My name is {ctx.client_full_name}. I am writing pursuant to the Fair Credit Reporting Act (FCRA), 15 U.S.C. § 1681 et seq., specifically my rights under § 611, to formally dispute an item appearing on my credit report.

My information:
Name: {ctx.client_full_name}
Address: {ctx.client_address_line1}, {ctx.client_city}, {ctx.client_state} {ctx.client_zip_code}
SSN (last 4): {ctx.client_ssn_last4}

DISPUTED ITEM:
Creditor: {ctx.creditor_name}
Account Number: {ctx.account_number_masked}

I dispute this item because it {reason_narrative}.

Specifically: {ctx.item_description}

Under FCRA § 611, you are required to conduct a reasonable investigation of this dispute within 30 days of receipt of this letter. If the information cannot be verified, it must be deleted from my credit file immediately. If the investigation confirms inaccuracies, the item must be corrected.

Please provide written confirmation of the results of your investigation and a copy of my updated credit report reflecting any corrections made.

Thank you for your prompt attention to this matter.

Sincerely,

{ctx.client_full_name}
{ctx.client_address_line1}
{ctx.client_city}, {ctx.client_state} {ctx.client_zip_code}
"""
