"""
Credit Report API Routes
GET/POST credit reports, tracking, scoring
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credit", tags=["credit"])

@router.post("/pull-report")
async def pull_credit_report(
    client_id: str,
    bureaus: List[str] = ["equifax", "experian", "transunion"],
    background_tasks: BackgroundTasks = None,
    db: Session = Depends()
):
    """
    Pull credit report from specified bureaus
    Runs in background, updates database
    """
    try:
        from api.credit_bureaus.client_factory import get_bureau_clients
        from models.credit import CreditReport
        from models.client import ClientProfile
        
        # Get client
        client = db.query(ClientProfile).filter(
            ClientProfile.id == client_id
        ).first()
        
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Pull reports in background
        background_tasks.add_task(
            pull_reports_background,
            client_id,
            client.ssn_encrypted,
            bureaus
        )
        
        return {
            "success": True,
            "message": "Credit report pull started",
            "client_id": client_id,
            "bureaus": bureaus,
            "status": "processing"
        }
    
    except Exception as e:
        logger.error(f"Error pulling report: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/report/{client_id}")
async def get_credit_report(client_id: str, db: Session = Depends()):
    """
    Get latest credit report for client
    """
    try:
        from models.credit import CreditReport
        
        # Get most recent report from each bureau
        reports = db.query(CreditReport).filter(
            CreditReport.client_id == client_id
        ).order_by(CreditReport.pull_timestamp.desc()).all()
        
        if not reports:
            raise HTTPException(status_code=404, detail="No reports found")
        
        # Group by bureau
        latest_by_bureau = {}
        for report in reports:
            if report.bureau not in latest_by_bureau:
                latest_by_bureau[report.bureau] = report
        
        return {
            "success": True,
            "client_id": client_id,
            "reports": [
                {
                    "bureau": report.bureau,
                    "score": report.score,
                    "pulled_at": report.pull_timestamp.isoformat(),
                    "report_date": report.report_date.isoformat() if report.report_date else None
                }
                for report in latest_by_bureau.values()
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting report: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/score-history/{client_id}")
async def get_score_history(client_id: str, days: int = 90, db: Session = Depends()):
    """
    Get credit score history (trending)
    """
    try:
        from models.credit import CreditReportSnapshot
        
        since = datetime.now() - timedelta(days=days)
        
        snapshots = db.query(CreditReportSnapshot).filter(
            CreditReportSnapshot.client_id == client_id,
            CreditReportSnapshot.snapshot_date >= since.date()
        ).order_by(CreditReportSnapshot.snapshot_date).all()
        
        return {
            "success": True,
            "client_id": client_id,
            "history": [
                {
                    "date": snapshot.snapshot_date.isoformat(),
                    "equifax": snapshot.equifax_score,
                    "experian": snapshot.experian_score,
                    "transunion": snapshot.transunion_score,
                    "average": snapshot.average_score
                }
                for snapshot in snapshots
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/items/{client_id}")
async def get_credit_items(client_id: str, db: Session = Depends()):
    """
    Get all credit items (tradelines, inquiries, negative items)
    """
    try:
        from models.credit import Tradeline, Inquiry, NegativeItem
        
        tradelines = db.query(Tradeline).filter(
            Tradeline.client_id == client_id
        ).all()
        
        inquiries = db.query(Inquiry).filter(
            Inquiry.client_id == client_id
        ).all()
        
        negative_items = db.query(NegativeItem).filter(
            NegativeItem.client_id == client_id
        ).all()
        
        return {
            "success": True,
            "client_id": client_id,
            "tradelines": [
                {
                    "id": str(t.id),
                    "account_type": t.account_type,
                    "creditor": t.creditor_name,
                    "balance": float(t.current_balance) if t.current_balance else 0,
                    "status": t.status,
                    "payment_status": t.payment_status
                }
                for t in tradelines
            ],
            "inquiries": [
                {
                    "id": str(i.id),
                    "type": i.inquiry_type,
                    "inquirer": i.inquirer_name,
                    "date": i.inquiry_date.isoformat() if i.inquiry_date else None
                }
                for i in inquiries
            ],
            "negative_items": [
                {
                    "id": str(n.id),
                    "type": n.item_type,
                    "creditor": n.creditor_name,
                    "amount": float(n.amount) if n.amount else 0,
                    "status": n.status,
                    "date": n.reported_date.isoformat() if n.reported_date else None
                }
                for n in negative_items
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting items: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

# ========================================
# BACKGROUND TASKS
# ========================================

def pull_reports_background(client_id: str, ssn: str, bureaus: List[str]):
    """Background task to pull reports from bureaus"""
    from api.credit_bureaus.client_factory import get_bureau_clients
    from models.credit import CreditReport, CreditReportSnapshot
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # New DB connection for background task
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        clients = get_bureau_clients()
        
        for bureau in bureaus:
            bureau_client = clients.get(bureau.lower())
            if not bureau_client:
                logger.warning(f"Bureau {bureau} not configured")
                continue
            
            # Pull report
            result = bureau_client.get_consumer_report(
                ssn=ssn,
                dob="",  # Get from client profile in real implementation
                first_name="",
                last_name="",
                address=""
            )
            
            if result.get("success"):
                # Store report
                report = CreditReport(
                    client_id=client_id,
                    bureau=bureau,
                    report_data=result.get("report_data"),
                    score=result.get("score"),
                    pull_timestamp=datetime.now()
                )
                db.add(report)
        
        db.commit()
        logger.info(f"Reports pulled for client {client_id}")
    
    except Exception as e:
        logger.error(f"Error pulling reports: {str(e)}")
        db.rollback()
    
    finally:
        db.close()
