"""
AI-Powered Dispute Letter Generation
Uses OpenAI GPT-4 to generate personalized, compliant dispute letters
"""

import os
import openai
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")

DISPUTE_LETTER_PROMPTS = {
    "inaccurate": """Generate a professional dispute letter for an inaccurate item on a credit report.
The item is: {item_description}
The account: {account_name}
The issue: {issue_description}

The letter must:
- Be professional and factual
- Reference the Fair Credit Reporting Act (FCRA)
- Request immediate investigation
- Not make false claims
- Be under 500 words
- Include the consumer's statement: {consumer_statement}""",
    
    "not_mine": """Generate a professional identity theft/not mine dispute letter.
Item: {item_description}
Account: {account_name}

The letter must:
- Clearly state this is not the consumer's account
- Reference FCRA section 611
- Request removal
- Suggest potential identity theft
- Professional tone
- Under 500 words
- Include: {consumer_statement}""",
    
    "outdated": """Generate a professional dispute letter for obsolete/outdated items.
Item: {item_description}
Account: {account_name}
Reporting date: {reporting_date}

The letter must:
- Reference FCRA 7-year rule
- State item should be removed
- Calculate reporting expiration
- Professional tone
- Under 500 words
- Include: {consumer_statement}""",
    
    "duplicate": """Generate a dispute letter for duplicate reporting.
Original item: {item_description}
Duplicate account: {account_name}

The letter must:
- Clearly identify duplication
- Reference FCRA section 611
- Request removal of duplicate
- Professional tone
- Under 500 words
- Include: {consumer_statement}"""
}

def generate_dispute_letter(
    client_id: str,
    negative_item: Dict,
    dispute_reason: str,
    client_statement: str
) -> str:
    """
    Generate a dispute letter using OpenAI GPT-4
    
    Args:
        client_id: Client UUID
        negative_item: Dict with {description, account_name, type, date, etc}
        dispute_reason: 'inaccurate', 'not_mine', 'outdated', 'duplicate'
        client_statement: Client's own statement about the item
    
    Returns:
        Generated dispute letter text
    """
    try:
        # Get appropriate prompt
        prompt_template = DISPUTE_LETTER_PROMPTS.get(dispute_reason.lower())
        if not prompt_template:
            dispute_reason = "inaccurate"  # Default
            prompt_template = DISPUTE_LETTER_PROMPTS["inaccurate"]
        
        # Format the prompt with item details
        prompt = prompt_template.format(
            item_description=negative_item.get("description", "Unknown item"),
            account_name=negative_item.get("creditor_name", "Unknown creditor"),
            issue_description=negative_item.get("status", ""),
            consumer_statement=client_statement or "I dispute this item as inaccurate.",
            reporting_date=negative_item.get("reported_date", "Unknown"),
            account_name=negative_item.get("creditor_name", "")
        )
        
        # Call OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at writing professional, legally compliant credit dispute letters that follow FCRA requirements. Generate clear, factual letters without making false claims."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        letter_content = response.choices[0].message.content
        
        logger.info(f"Generated dispute letter for client {client_id}", extra={
            "dispute_reason": dispute_reason,
            "item_type": negative_item.get("type")
        })
        
        return letter_content
    
    except Exception as e:
        logger.error(f"Error generating letter: {str(e)}")
        # Return template letter as fallback
        return generate_template_letter(negative_item, dispute_reason, client_statement)

def generate_template_letter(
    negative_item: Dict,
    dispute_reason: str,
    client_statement: str
) -> str:
    """
    Generate a template-based letter (fallback if OpenAI unavailable)
    """
    template = f"""
DISPUTE LETTER

Date: {os.popen('date').read().strip()}

To: {negative_item.get('creditor_name', 'Credit Reporting Agency')}

RE: DISPUTE OF INACCURATE INFORMATION

Dear Sir or Madam:

I am writing to dispute the accuracy of the following item on my credit report:

Item: {negative_item.get('description', 'Unknown')}
Account: {negative_item.get('creditor_name', 'Unknown')}
Status: {negative_item.get('status', 'Unknown')}

Reason for Dispute: {dispute_reason.upper()}

{client_statement}

Pursuant to the Fair Credit Reporting Act (FCRA), I request that you:
1. Conduct a thorough investigation into this item
2. Remove or correct this information if found to be inaccurate
3. Notify me in writing of the results of your investigation

Please respond within 30 days as required by law.

Sincerely,
[Consumer Name]
[Address]
[Phone]
[Email]
"""
    return template.strip()
