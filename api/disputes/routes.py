"""
Dispute Management API Routes
POST /api/disputes/create - Create new dispute case
GET /api/disputes/{id}/status - Get dispute status
GET /api/disputes - List disputes for client
POST /api/disputes/{id}/approve-letter - Approve dispute letter before filing
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disputes", tags=["disputes"])

# ========================================
# REQUEST/RESPONSE MODELS
# ========================================

class CreateDisputeRequest(BaseModel):
    client_id: str
    negative_item_id: str
    bureaus: list = ["equifax", "experian", "transunion"]  # Which bureaus to dispute
    dispute_reason: str  # 'inaccurate', 'not_mine', 'outdated', 'duplicate'
    client_statement: Optional[str] = None

class DisputeLetterResponse(BaseModel):
    letter_id: str
    content: str
    generated_at: str
    requires_approval: bool
    compliance_status: str

class ApproveLetterRequest(BaseModel):
    letter_id: str
    approved: bool
    notes: Optional[str] = None

class DisputeStatusResponse(BaseModel):
    dispute_id: str
    status: str  # 'filed', 'investigating', 'resolved'
    filed_date: str
    investigation_deadline: str
    bureau_responses: list
    outcome: Optional[str]

# ========================================
# ENDPOINTS
# ========================================

@router.post("/create")
async def create_dispute(
    request: CreateDisputeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends()
):
    """
    Create new dispute case
    1. Identify negative item
    2. Generate dispute letter (AI)
    3. Check compliance
    4. Await client approval
    5. File to bureau
    """
    try:
        from models.dispute import DisputeCase, DisputeLetter
        from models.negative_items import NegativeItem
        from services.letter_generation import generate_dispute_letter
        from services.compliance_check import check_compliance
        from api.credit_bureaus.client_factory import get_bureau_clients
        
        # 1. Get negative item
        item = db.query(NegativeItem).filter(
            NegativeItem.id == request.negative_item_id,
            NegativeItem.client_id == request.client_id
        ).first()
        
        if not item:
            raise HTTPException(status_code=404, detail="Negative item not found")
        
        # 2. Create dispute case
        dispute_case = DisputeCase(
            client_id=request.client_id,
            negative_item_id=request.negative_item_id,
            dispute_reason=request.dispute_reason,
            filed_date=datetime.now(),
            investigation_deadline=datetime.now() + timedelta(days=30),
            status='draft'  # Not filed yet
        )
        db.add(dispute_case)
        db.flush()
        
        # 3. Generate dispute letter (AI)
        letter_content = generate_dispute_letter(
            client_id=request.client_id,
            negative_item=item,
            dispute_reason=request.dispute_reason,
            client_statement=request.client_statement
        )
        
        # 4. Check compliance
        compliance_result = check_compliance(letter_content)
        
        # 5. Create dispute letter record
        dispute_letter = DisputeLetter(
            dispute_case_id=dispute_case.id,
            letter_content=letter_content,
            generated_by='ai_generated',
            compliance_checked=True,
            compliance_result=compliance_result
        )
        db.add(dispute_letter)
        db.commit()
        
        # Log action
        from models.audit import AuditTrail
        audit = AuditTrail(
            action='dispute_created',
            actor_type='system',
            subject_type='dispute',
            subject_id=str(dispute_case.id),
            details={
                'client_id': request.client_id,
                'item_id': request.negative_item_id,
                'reason': request.dispute_reason
            }
        )
        db.add(audit)
        db.commit()
        
        return {
            "success": True,
            "dispute_id": str(dispute_case.id),
            "status": "draft",
            "letter_id": str(dispute_letter.id),
            "requires_approval": True,
            "compliance_status": compliance_result.get("status"),
            "next_step": "Client must review and approve letter"
        }
    
    except Exception as e:
        logger.error(f"Error creating dispute: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/{dispute_id}/approve-letter")
async def approve_dispute_letter(
    dispute_id: str,
    request: ApproveLetterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends()
):
    """
    Client approves dispute letter
    Then system files to bureau
    """
    try:
        from models.dispute import DisputeCase, DisputeLetter
        from api.credit_bureaus.client_factory import get_bureau_clients
        from models.client import ClientProfile
        
        # Get dispute
        dispute = db.query(DisputeCase).filter(
            DisputeCase.id == dispute_id
        ).first()
        
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        
        # Get letter
        letter = db.query(DisputeLetter).filter(
            DisputeLetter.dispute_case_id == dispute_id
        ).first()
        
        if not letter:
            raise HTTPException(status_code=404, detail="Letter not found")
        
        if not request.approved:
            # Client rejected
            dispute.status = 'cancelled'
            db.commit()
            return {
                "success": True,
                "message": "Dispute cancelled"
            }
        
        # Client approved - now file to bureaus
        letter.approved_by = "client"  # In real system, get user ID
        letter.approval_timestamp = datetime.now()
        
        # Get client for SSN and bureau clients
        client = db.query(ClientProfile).filter(
            ClientProfile.id == dispute.client_id
        ).first()
        
        # File to bureaus in background
        background_tasks.add_task(
            file_dispute_to_bureaus,
            dispute_id,
            client.ssn_encrypted,
            letter.letter_content,
            dispute.bureaus
        )
        
        # Update status
        dispute.status = 'filing'
        db.commit()
        
        # Log action
        from models.audit import AuditTrail
        audit = AuditTrail(
            action='dispute_approved',
            actor_type='human',
            subject_type='dispute',
            subject_id=str(dispute_id),
            details={'letter_approved': True}
        )
        db.add(audit)
        db.commit()
        
        return {
            "success": True,
            "dispute_id": dispute_id,
            "status": "filing",
            "message": "Dispute approved, filing to bureaus now"
        }
    
    except Exception as e:
        logger.error(f"Error approving letter: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/{dispute_id}/status")
async def get_dispute_status(dispute_id: str, db: Session = Depends()):
    """
    Get dispute status and investigation progress
    """
    try:
        from models.dispute import DisputeCase, BureauResponse
        
        dispute = db.query(DisputeCase).filter(
            DisputeCase.id == dispute_id
        ).first()
        
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        
        # Get bureau responses
        responses = db.query(BureauResponse).filter(
            BureauResponse.dispute_case_id == dispute_id
        ).all()
        
        return {
            "success": True,
            "dispute_id": dispute_id,
            "status": dispute.status,
            "filed_date": dispute.filed_date.isoformat() if dispute.filed_date else None,
            "investigation_deadline": dispute.investigation_deadline.isoformat(),
            "days_remaining": (dispute.investigation_deadline - datetime.now()).days,
            "outcome": dispute.outcome,
            "bureau_responses": [
                {
                    "bureau": r.bureau,
                    "response_date": r.response_date.isoformat(),
                    "outcome": r.outcome,
                    "summary": r.investigation_summary
                }
                for r in responses
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting dispute status: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("")
async def list_disputes(client_id: str, db: Session = Depends()):
    """
    List all disputes for a client
    """
    try:
        from models.dispute import DisputeCase
        
        disputes = db.query(DisputeCase).filter(
            DisputeCase.client_id == client_id
        ).order_by(DisputeCase.filed_date.desc()).all()
        
        return {
            "success": True,
            "disputes": [
                {
                    "id": str(d.id),
                    "status": d.status,
                    "filed_date": d.filed_date.isoformat() if d.filed_date else None,
                    "outcome": d.outcome,
                    "reason": d.dispute_reason
                }
                for d in disputes
            ]
        }
    
    except Exception as e:
        logger.error(f"Error listing disputes: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

# ========================================
# BACKGROUND TASKS
# ========================================

def file_dispute_to_bureaus(dispute_id: str, ssn: str, letter_content: str, bureaus: list):
    """
    Background task: File dispute to each bureau
    """
    from api.credit_bureaus.client_factory import get_bureau_clients
    
    clients = get_bureau_clients()
    
    for bureau in bureaus:
        try:
            client = clients.get(bureau)
            if client:
                result = client.file_dispute(
                    ssn=ssn,
                    item_id="item_id",  # From dispute record
                    dispute_reason="dispute_reason",
                    consumer_statement=letter_content
                )
                
                logger.info(f"Filed dispute {dispute_id} to {bureau}: {result}")
        
        except Exception as e:
            logger.error(f"Error filing dispute to {bureau}: {str(e)}")
