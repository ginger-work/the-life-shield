"""
Compliance Checking Service
Uses Claude API to verify FCRA/CROA compliance before filing disputes
"""

import os
import anthropic
from typing import Dict
import logging

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def check_compliance(letter_content: str) -> Dict:
    """
    Check dispute letter for FCRA and CROA compliance
    
    Args:
        letter_content: Full dispute letter text
    
    Returns:
        {
            "status": "approved" | "rejected" | "warning",
            "violations": [...],
            "warnings": [...],
            "approved": bool,
            "reason": str
        }
    """
    try:
        prompt = f"""Review this dispute letter for compliance with the Fair Credit Reporting Act (FCRA) and Credit Repair Organizations Act (CROA).

LETTER:
{letter_content}

Check for:
1. FCRA violations (incorrect consumer rights, improper language)
2. CROA violations (guarantees of outcome, deceptive claims)
3. False claims or misrepresentations
4. Threats or aggressive language
5. Missing required legal references

Respond in JSON format:
{{
    "status": "approved|warning|rejected",
    "violations": [list of violations],
    "warnings": [list of warnings],
    "approved": true|false,
    "reason": "explanation"
}}"""
        
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse response
        import json
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                # Fallback if no JSON found
                result = {
                    "status": "warning",
                    "approved": False,
                    "violations": [],
                    "warnings": ["Could not parse compliance check response"],
                    "reason": "Manual review recommended"
                }
        except json.JSONDecodeError:
            result = {
                "status": "warning",
                "approved": False,
                "violations": [],
                "warnings": ["Compliance check parsing failed"],
                "reason": "Manual review recommended"
            }
        
        logger.info(f"Compliance check completed", extra={
            "status": result.get("status"),
            "approved": result.get("approved"),
            "violations_count": len(result.get("violations", []))
        })
        
        return result
    
    except Exception as e:
        logger.error(f"Error checking compliance: {str(e)}")
        return {
            "status": "warning",
            "approved": False,
            "violations": [],
            "warnings": [f"Compliance check failed: {str(e)}"],
            "reason": "Error during compliance check - manual review required"
        }

def check_fcra_compliance(text: str) -> Dict:
    """Check for FCRA-specific violations"""
    fcra_violations = []
    
    # Check for common FCRA violations
    violation_patterns = {
        "guarantee": ["guaranteed", "guarantee", "ensure removal", "will remove"],
        "misleading": ["only way", "fastest", "never denied"],
        "consumer_rights": ["you have no rights", "cannot dispute"],
        "false_claims": ["sue on your behalf", "certified attorney"]
    }
    
    text_lower = text.lower()
    for violation_type, patterns in violation_patterns.items():
        for pattern in patterns:
            if pattern in text_lower:
                fcra_violations.append(f"Potential {violation_type}: '{pattern}'")
    
    return {
        "violations": fcra_violations,
        "compliant": len(fcra_violations) == 0
    }

def check_croa_compliance(text: str) -> Dict:
    """Check for CROA-specific violations"""
    croa_violations = []
    
    # Check for common CROA violations
    violation_patterns = {
        "advance_fees": ["$", "fee", "cost", "charge"],  # Simplified
        "misrepresentation": ["damaged", "removed", "deleted"],
        "false_success": ["100% success", "guaranteed results"]
    }
    
    text_lower = text.lower()
    for violation_type, patterns in violation_patterns.items():
        for pattern in patterns:
            if pattern in text_lower:
                # Only flag if it's likely a violation (context-dependent)
                if violation_type == "misrepresentation":
                    croa_violations.append(f"Check {violation_type}: '{pattern}'")
    
    return {
        "violations": croa_violations,
        "compliant": len(croa_violations) == 0
    }
