"""
iSoftPull Client - Real-time soft pull credit monitoring (no score impact)
"""

import requests
from typing import Dict, List
from datetime import datetime
import logging
from .base import CreditBureauClient

logger = logging.getLogger(__name__)

class iSoftPullClient(CreditBureauClient):
    """iSoftPull API client - soft pull monitoring"""
    
    def __init__(self, api_key: str, api_url: str = "https://api.isoftpull.com"):
        super().__init__(api_key, None, api_url)
        self.authenticated = True  # iSoftPull uses simple API key auth
    
    def authenticate(self) -> bool:
        """iSoftPull doesn't require explicit authentication"""
        self.authenticated = True
        return True
    
    def get_soft_pull(self, ssn: str, dob: str) -> Dict:
        """
        Get soft pull credit score (no impact on score)
        Faster than full report pull
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "ssn": ssn,
                "date_of_birth": dob
            }
            
            response = requests.post(
                f"{self.api_url}/v1/softpull/score",
                headers=headers,
                json=payload,
                timeout=5  # Soft pulls are fast
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_action("get_soft_pull", {
                    "ssn": ssn[-4:],
                    "success": True,
                    "score": data.get("score")
                })
                
                return {
                    "success": True,
                    "score": data.get("score"),
                    "pulled_at": datetime.now().isoformat(),
                    "no_score_impact": True
                }
            else:
                error_msg = response.json().get("error", response.text)
                self.log_action("get_soft_pull", {
                    "success": False,
                    "status": response.status_code
                })
                
                return {
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            return self.handle_error(e, "get_soft_pull")
    
    def setup_monitoring_alerts(self, ssn: str, dob: str, webhook_url: str) -> Dict:
        """
        Set up real-time credit monitoring alerts
        iSoftPull will POST to webhook_url when changes detected
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "ssn": ssn,
                "date_of_birth": dob,
                "webhook_url": webhook_url,
                "alert_types": [
                    "new_inquiry",
                    "new_account",
                    "negative_item",
                    "score_change"
                ]
            }
            
            response = requests.post(
                f"{self.api_url}/v1/monitoring/setup",
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.log_action("setup_monitoring", {
                    "ssn": ssn[-4:],
                    "success": True,
                    "monitor_id": data.get("monitor_id")
                })
                
                return {
                    "success": True,
                    "monitor_id": data.get("monitor_id"),
                    "message": "Monitoring enabled - alerts will be sent to webhook"
                }
            else:
                error_msg = response.json().get("error", response.text)
                self.log_action("setup_monitoring", {
                    "success": False,
                    "status": response.status_code
                })
                
                return {
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            return self.handle_error(e, "setup_monitoring")
    
    def get_recent_changes(self, ssn: str, days: int = 7) -> List[Dict]:
        """
        Get recent changes to credit file (last N days)
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.api_url}/v1/monitoring/changes",
                headers=headers,
                params={
                    "ssn": ssn,
                    "days": days
                },
                timeout=10
            )
            
            if response.status_code == 200:
                changes = response.json().get("changes", [])
                self.log_action("get_recent_changes", {
                    "ssn": ssn[-4:],
                    "changes_count": len(changes),
                    "success": True
                })
                
                return changes
            else:
                self.log_action("get_recent_changes", {
                    "success": False,
                    "status": response.status_code
                })
                return []
        
        except Exception as e:
            self.handle_error(e, "get_recent_changes")
            return []
    
    # iSoftPull doesn't support dispute filing directly
    # Use full bureau clients (Equifax, Experian, TransUnion) for disputes
    
    def get_consumer_report(self, ssn: str, dob: str, first_name: str = "", last_name: str = "", address: str = "") -> Dict:
        """iSoftPull doesn't support full reports - use soft pull instead"""
        return self.get_soft_pull(ssn, dob)
    
    def file_dispute(self, ssn: str, item_id: str, dispute_reason: str, consumer_statement: str) -> Dict:
        """iSoftPull doesn't support dispute filing"""
        return {
            "success": False,
            "error": "iSoftPull is monitoring only. Use Equifax, Experian, or TransUnion for dispute filing."
        }
    
    def get_dispute_status(self, case_number: str, ssn: str) -> Dict:
        """iSoftPull doesn't support dispute tracking"""
        return {
            "success": False,
            "error": "iSoftPull is monitoring only. Use Equifax, Experian, or TransUnion for dispute status."
        }
    
    def get_file_changes(self, ssn: str, last_check_date) -> List[Dict]:
        """Alias for get_recent_changes"""
        return self.get_recent_changes(ssn, days=7)
