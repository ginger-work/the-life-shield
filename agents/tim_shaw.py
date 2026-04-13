"""
TIM SHAW - Persistent Client Agent
The face of The Life Shield to every client
Backed by 5 specialist engines (analyst, compliance, scheduler, recommendation, supervisor)
"""

from typing import Dict, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class TimShaw:
    """Tim Shaw - Persistent client-facing AI agent"""
    
    def __init__(self, client_id: str, db_session):
        self.client_id = client_id
        self.db = db_session
        self.name = "Tim Shaw"
        self.role = "Client Success Agent"
        self.tone = "warm, professional, helpful"
        self.disclosure = "I'm Tim Shaw, an AI Client Agent. Your account is monitored by human staff."
    
    def respond_to_message(self, message: str, channel: str = "portal") -> Dict:
        """
        Main entry point: client sends message, Tim Shaw responds
        Routes to specialist engines internally
        """
        try:
            # 1. Understand intent & context
            intent = self._analyze_intent(message)
            
            # 2. Route to appropriate specialist engine
            specialist_response = self._route_to_specialist(intent, message)
            
            # 3. Format response in Tim Shaw's voice
            response = self._format_response(specialist_response, channel)
            
            # 4. Check compliance
            compliance_ok = self._check_compliance(response)
            if not compliance_ok:
                response = "I need to review this with my team. They'll get back to you shortly."
            
            # 5. Log interaction
            self._log_interaction(message, response, channel, intent)
            
            return {
                "success": True,
                "agent": self.name,
                "response": response,
                "channel": channel,
                "requires_human": not compliance_ok
            }
        
        except Exception as e:
            logger.error(f"Error in Tim Shaw response: {str(e)}")
            return {
                "success": False,
                "error": "I'll connect you with a human specialist.",
                "escalate_to_human": True
            }
    
    def _analyze_intent(self, message: str) -> Dict:
        """Analyze what the client is asking about"""
        message_lower = message.lower()
        
        intent_map = {
            "dispute": ["dispute", "remove", "item", "wrong", "inaccurate"],
            "score": ["score", "credit", "improve", "trending"],
            "dispute_status": ["status", "investigation", "update", "progress"],
            "coaching": ["help", "budget", "debt", "strategy", "call"],
            "payment": ["payment", "subscription", "billing", "charge"],
            "legal": ["lawsuit", "lawyer", "court", "attorney"]
        }
        
        detected_intent = "general"
        for intent, keywords in intent_map.items():
            if any(kw in message_lower for kw in keywords):
                detected_intent = intent
                break
        
        return {
            "intent": detected_intent,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
    
    def _route_to_specialist(self, intent: Dict, message: str) -> Dict:
        """Route to the appropriate specialist engine"""
        from agents.specialist_engines import (
            CreditAnalystEngine,
            ComplianceEngine,
            SchedulerEngine,
            RecommendationEngine,
            SupervisorEngine
        )
        
        intent_type = intent.get("intent")
        
        if intent_type in ["dispute", "dispute_status"]:
            specialist = CreditAnalystEngine(self.client_id, self.db)
            return specialist.analyze(message)
        
        elif intent_type == "score":
            specialist = CreditAnalystEngine(self.client_id, self.db)
            return specialist.score_analysis(message)
        
        elif intent_type == "coaching":
            specialist = SchedulerEngine(self.client_id, self.db)
            return specialist.suggest_session(message)
        
        elif intent_type == "payment":
            specialist = ComplianceEngine(self.client_id, self.db)
            return specialist.check_payment_query(message)
        
        elif intent_type == "legal":
            specialist = SupervisorEngine(self.client_id, self.db)
            return specialist.escalate(message, "legal_threat")
        
        else:
            # General question - provide helpful guidance
            return {
                "response": "How can I help with your credit today? I can assist with disputes, coaching, or checking your progress.",
                "needs_escalation": False
            }
    
    def _format_response(self, specialist_response: Dict, channel: str) -> str:
        """Format specialist response in Tim Shaw's voice"""
        base_response = specialist_response.get("response", "")
        
        # Add AI disclosure if it's the first message of session
        if channel == "voice":
            prefix = f"Hi! This is {self.name}, an AI agent at The Life Shield. {self.disclosure}\n\n"
        elif channel == "video":
            prefix = f"Welcome. I'm {self.name}. {self.disclosure}\n\n"
        else:
            prefix = ""
        
        return prefix + base_response
    
    def _check_compliance(self, response: str) -> bool:
        """Check if response complies with FCRA/CROA"""
        from services.compliance_check import check_fcra_compliance
        
        result = check_fcra_compliance(response)
        return result.get("compliant", True)
    
    def _log_interaction(self, message: str, response: str, channel: str, intent: Dict):
        """Log interaction for audit trail"""
        from models.communication import CommunicationLog
        
        log = CommunicationLog(
            client_id=self.client_id,
            agent_id="tim-shaw",
            channel=channel,
            message_content=message,
            is_outbound=False,
            status="received",
            created_at=datetime.now()
        )
        self.db.add(log)
        
        response_log = CommunicationLog(
            client_id=self.client_id,
            agent_id="tim-shaw",
            channel=channel,
            message_content=response,
            is_outbound=True,
            status="sent",
            created_at=datetime.now()
        )
        self.db.add(response_log)
        self.db.commit()
        
        logger.info(f"Tim Shaw interaction logged", extra={
            "client_id": self.client_id,
            "intent": intent.get("intent"),
            "channel": channel
        })
