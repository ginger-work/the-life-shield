"""
Base credit bureau client - Abstract interface for all bureaus
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CreditBureauClient(ABC):
    """Abstract base class for credit bureau clients"""
    
    def __init__(self, api_key: str, api_secret: Optional[str] = None, api_url: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = api_url
        self.name = self.__class__.__name__
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with bureau API"""
        pass
    
    @abstractmethod
    def get_consumer_report(self, ssn: str, dob: str, first_name: str, last_name: str, address: str) -> Dict:
        """Pull consumer credit report"""
        pass
    
    @abstractmethod
    def file_dispute(self, ssn: str, item_id: str, dispute_reason: str, consumer_statement: str) -> Dict:
        """File dispute with bureau"""
        pass
    
    @abstractmethod
    def get_dispute_status(self, case_number: str, ssn: str) -> Dict:
        """Check dispute investigation status"""
        pass
    
    @abstractmethod
    def get_file_changes(self, ssn: str, last_check_date: datetime) -> List[Dict]:
        """Get changes to consumer file since last check"""
        pass
    
    def log_action(self, action: str, details: Dict):
        """Log API action for audit trail"""
        logger.info(f"{self.name} - {action}", extra={"details": details})
    
    def handle_error(self, error: Exception, context: str) -> Dict:
        """Handle and log API errors"""
        logger.error(f"{self.name} Error in {context}: {str(error)}")
        return {
            "success": False,
            "error": str(error),
            "bureau": self.name,
            "context": context
        }
