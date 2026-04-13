"""
TransUnion API Client - Pull reports, file disputes, monitor investigations
"""

import requests
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import logging
from .base import CreditBureauClient

logger = logging.getLogger(__name__)

class TransUnionClient(CreditBureauClient):
    """TransUnion API client implementation"""
    
    def __init__(self, api_key: str, api_secret: str, api_url: str = "https://api.transunion.com"):
        super().__init__(api_key, api_secret, api_url)
        self.session_token = None
        self.authenticated = False
    
    def authenticate(self) -> bool:
        """Authenticate with TransUnion API"""
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.api_url}/authentication/v1/authenticate",
                headers=headers,
                json={"api_secret": self.api_secret},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get("token")
                self.authenticated = True
                self.log_action("authenticate", {"success": True})
                return True
            else:
                self.log_action("authenticate", {"success": False, "status": response.status_code})
                return False
        
        except Exception as e:
            return bool(self.handle_error(e, "authenticate"))
    
    def get_consumer_report(self, ssn: str, dob: str, first_name: str, last_name: str, address: str) -> Dict:
        """Pull consumer credit report from TransUnion"""
        if not self.authenticated:
            self.authenticate()
        
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "consumer": {
                    "ssn": ssn,
                    "date_of_birth": dob,
                    "first_name": first_name,
                    "last_name": last_name,
                    "address": address
                }
            }
            
            response = requests.post(
                f"{self.api_url}/creditreporting/v1/consumers/creditreport",
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                report_data = response.json()
                self.log_action("get_consumer_report", {
                    "ssn": ssn[-4:],
                    "success": True
                })
                
                return {
                    "success": True,
                    "bureau": "transunion",
                    "report_data": report_data,
                    "score": report_data.get("credit_score"),
                    "pulled_at": datetime.now().isoformat()
                }
            else:
                error_msg = response.json().get("error", response.text)
                self.log_action("get_consumer_report", {
                    "success": False,
                    "status": response.status_code
                })
                
                return {
                    "success": False,
                    "error": error_msg,
                    "bureau": "transunion"
                }
        
        except Exception as e:
            return self.handle_error(e, "get_consumer_report")
    
    def file_dispute(self, ssn: str, item_id: str, dispute_reason: str, consumer_statement: str) -> Dict:
        """File dispute with TransUnion"""
        if not self.authenticated:
            self.authenticate()
        
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "consumer": {"ssn": ssn},
                "dispute_request": {
                    "item_id": item_id,
                    "reason_code": dispute_reason,
                    "consumer_statement": consumer_statement,
                    "date_filed": datetime.now().isoformat()
                }
            }
            
            response = requests.post(
                f"{self.api_url}/disputes/v1/file",
                headers=headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                dispute_data = response.json()
                case_number = dispute_data.get("case_number")
                
                self.log_action("file_dispute", {
                    "ssn": ssn[-4:],
                    "item_id": item_id,
                    "case_number": case_number,
                    "success": True
                })
                
                return {
                    "success": True,
                    "bureau": "transunion",
                    "case_number": case_number,
                    "filed_at": datetime.now().isoformat(),
                    "investigation_deadline": (datetime.now() + timedelta(days=30)).isoformat()
                }
            else:
                error_msg = response.json().get("error", response.text)
                self.log_action("file_dispute", {
                    "success": False,
                    "status": response.status_code
                })
                
                return {
                    "success": False,
                    "error": error_msg,
                    "bureau": "transunion"
                }
        
        except Exception as e:
            return self.handle_error(e, "file_dispute")
    
    def get_dispute_status(self, case_number: str, ssn: str) -> Dict:
        """Check dispute investigation status"""
        if not self.authenticated:
            self.authenticate()
        
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.api_url}/disputes/v1/{case_number}",
                headers=headers,
                params={"ssn": ssn},
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                
                self.log_action("get_dispute_status", {
                    "case_number": case_number,
                    "status": status_data.get("status"),
                    "success": True
                })
                
                return {
                    "success": True,
                    "bureau": "transunion",
                    "case_number": case_number,
                    "status": status_data.get("status"),
                    "outcome": status_data.get("outcome"),
                    "last_update": status_data.get("last_update"),
                    "expected_resolution": status_data.get("expected_resolution_date")
                }
            else:
                error_msg = response.json().get("error", response.text)
                return {
                    "success": False,
                    "error": error_msg,
                    "bureau": "transunion"
                }
        
        except Exception as e:
            return self.handle_error(e, "get_dispute_status")
    
    def get_file_changes(self, ssn: str, last_check_date: datetime) -> List[Dict]:
        """Get changes to consumer file since last check"""
        if not self.authenticated:
            self.authenticate()
        
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.api_url}/creditreporting/v1/consumers/filechanges",
                headers=headers,
                params={
                    "ssn": ssn,
                    "since": last_check_date.isoformat()
                },
                timeout=10
            )
            
            if response.status_code == 200:
                changes = response.json().get("changes", [])
                self.log_action("get_file_changes", {
                    "ssn": ssn[-4:],
                    "changes_count": len(changes)
                })
                return changes
            else:
                self.log_action("get_file_changes", {
                    "success": False,
                    "status": response.status_code
                })
                return []
        
        except Exception as e:
            self.handle_error(e, "get_file_changes")
            return []
