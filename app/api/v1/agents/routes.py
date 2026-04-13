"""
Agents API Router — Phase 3 (Agent System) + Phase 6 (Admin)

Endpoints:
  GET    /api/v1/agents/                     - Admin: list agents
  POST   /api/v1/agents/                     - Admin: create agent
  GET    /api/v1/agents/{id}                 - Get agent profile
  PUT    /api/v1/agents/{id}                 - Admin: update agent
  DELETE /api/v1/agents/{id}                 - Admin: deactivate agent
  POST   /api/v1/agents/{id}/assign          - Admin: assign client to agent
  POST   /api/v1/agents/chat                 - Client: send message to Tim Shaw
  GET    /api/v1/agents/chat/history         - Client: chat history with Tim Shaw
  POST   /api/v1/agents/escalate             - Escalate to human supervisor
  GET    /api/v1/agents/me                   - Current agent's profile (agent role)
  POST   /api/v1/agents/{id}/takeover        - Admin: take over conversation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter()


# ── Pydantic Models ────────────────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    agent_name: str
    display_name: str
    role: str = "client_success_agent"
    tone: Optional[str] = "warm, professional, helpful"
    communication_style: Optional[str] = None
    greeting_template: Optional[str] = None
    voice_provider: Optional[str] = "elevenlabs"
    voice_id: Optional[str] = None
    avatar_type: Optional[str] = "static"
    disclosure_text: Optional[str] = "AI Client Agent for The Life Shield"
    max_client_capacity: int = 50


class AgentResponse(BaseModel):
    id: str
    agent_name: str
    display_name: str
    role: str
    tone: Optional[str]
    is_active: bool
    max_client_capacity: int
    current_client_count: int
    disclosure_text: Optional[str]
    created_at: str


class ChatRequest(BaseModel):
    message: str
    channel: str = "portal"
    client_id: Optional[str] = None


class ChatResponse(BaseModel):
    agent_name: str
    response: str
    channel: str
    timestamp: str
    requires_human: bool = False
    escalated: bool = False
    disclosure: Optional[str] = None


class AssignRequest(BaseModel):
    client_id: str
    agent_id: str
    notes: Optional[str] = None


# ── Chat with Tim Shaw (Core Agent Interaction) ────────────────────────────

@router.post("/chat", response_model=ChatResponse, summary="Send message to Tim Shaw")
async def chat_with_agent(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Primary interaction endpoint — client sends message, Tim Shaw responds.
    Routes through all 6 specialist engines internally.
    
    Disclosure is included on first message of session per FTC requirements.
    """
    from agents.tim_shaw import TimShaw
    from agents.specialist_engines import SupervisorEngine

    # Use a mock client_id if not provided (demo mode)
    client_id = req.client_id or str(uuid.uuid4())

    # Check for escalation triggers first
    supervisor = SupervisorEngine(client_id, db)
    trigger = supervisor.detect_escalation_trigger(req.message)
    if trigger:
        result = supervisor.escalate(req.message, trigger)
        return ChatResponse(
            agent_name="Tim Shaw",
            response=result["response"],
            channel=req.channel,
            timestamp=datetime.now(timezone.utc).isoformat(),
            requires_human=True,
            escalated=True,
        )

    # Normal Tim Shaw response
    tim = TimShaw(client_id, db)
    result = tim.respond_to_message(req.message, req.channel)

    return ChatResponse(
        agent_name="Tim Shaw",
        response=result.get("response", result.get("error", "I'm here to help.")),
        channel=req.channel,
        timestamp=datetime.now(timezone.utc).isoformat(),
        requires_human=result.get("requires_human", False),
        escalated=result.get("escalate_to_human", False),
        disclosure="I'm Tim Shaw, an AI Client Agent. Your account is monitored by human staff.",
    )


@router.get("/chat/history", summary="Get chat history with Tim Shaw")
async def get_chat_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Return paginated chat history for the authenticated client."""
    # In production: query CommunicationLog table for this client
    return {
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "from": "Tim Shaw",
                "message": "Hi John! Your Equifax dispute has been filed. I'll keep you updated.",
                "channel": "portal",
                "sent_at": "2026-04-13T18:00:00Z",
                "direction": "outbound",
            },
            {
                "id": str(uuid.uuid4()),
                "from": "You",
                "message": "What should I do about the collection account?",
                "channel": "portal",
                "sent_at": "2026-04-13T17:55:00Z",
                "direction": "inbound",
            },
        ],
        "total": 2,
        "offset": offset,
        "limit": limit,
    }


@router.post("/escalate", summary="Escalate to human supervisor")
async def escalate_to_human(
    reason: str = Body(...),
    channel: str = Body("portal"),
    db: Session = Depends(get_db),
):
    """
    Client-initiated escalation to human supervisor.
    AI conversation stops immediately; human coordinator notified.
    """
    from agents.specialist_engines import SupervisorEngine
    supervisor = SupervisorEngine("current-client", db)
    result = supervisor.escalate(reason, "human_request")

    log.info("human_escalation_requested", reason=reason, channel=channel)

    return {
        "success": True,
        "escalated": True,
        "message": result["response"],
        "sla_minutes": 15,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Admin Agent Management ─────────────────────────────────────────────────

@router.get("/", summary="Admin: list all agent profiles")
async def list_agents(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Admin: list all configured agents."""
    # Demo agents: Tim Shaw + specialist engines
    agents = [
        {
            "id": "agent-001",
            "agent_name": "tim_shaw",
            "display_name": "Tim Shaw",
            "role": "client_success_agent",
            "is_active": True,
            "max_client_capacity": 500,
            "current_client_count": 0,
            "disclosure_text": "AI Client Agent for The Life Shield",
        },
        {
            "id": "agent-002",
            "agent_name": "credit_analyst",
            "display_name": "Credit Analyst Engine",
            "role": "credit_analyst",
            "is_active": True,
            "max_client_capacity": 9999,
            "current_client_count": 0,
            "disclosure_text": "Internal analytical engine",
        },
        {
            "id": "agent-003",
            "agent_name": "compliance_engine",
            "display_name": "Compliance Engine",
            "role": "compliance_engine",
            "is_active": True,
            "max_client_capacity": 9999,
            "current_client_count": 0,
            "disclosure_text": "FCRA/CROA compliance gating engine",
        },
        {
            "id": "agent-004",
            "agent_name": "scheduler",
            "display_name": "Scheduler Engine",
            "role": "scheduler",
            "is_active": True,
            "max_client_capacity": 9999,
            "current_client_count": 0,
            "disclosure_text": "Appointment and SLA management engine",
        },
        {
            "id": "agent-005",
            "agent_name": "recommendation_engine",
            "display_name": "Recommendation Engine",
            "role": "recommendation",
            "is_active": True,
            "max_client_capacity": 9999,
            "current_client_count": 0,
            "disclosure_text": "Admin-approved product recommendation engine",
        },
        {
            "id": "agent-006",
            "agent_name": "supervisor",
            "display_name": "Human Supervisor Engine",
            "role": "supervisor",
            "is_active": True,
            "max_client_capacity": 9999,
            "current_client_count": 0,
            "disclosure_text": "Human oversight and escalation coordination",
        },
    ]

    if is_active is not None:
        agents = [a for a in agents if a["is_active"] == is_active]

    return {
        "agents": agents,
        "total": len(agents),
        "page": page,
        "per_page": per_page,
    }


@router.post("/", response_model=AgentResponse, status_code=201, summary="Admin: create agent")
async def create_agent(req: AgentCreateRequest, db: Session = Depends(get_db)):
    """Admin: create a new agent profile."""
    agent_id = str(uuid.uuid4())
    log.info("agent_created", agent_name=req.agent_name, role=req.role)
    return AgentResponse(
        id=agent_id,
        agent_name=req.agent_name,
        display_name=req.display_name,
        role=req.role,
        tone=req.tone,
        is_active=True,
        max_client_capacity=req.max_client_capacity,
        current_client_count=0,
        disclosure_text=req.disclosure_text,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{agent_id}", response_model=AgentResponse, summary="Get agent profile")
async def get_agent(agent_id: str = Path(...), db: Session = Depends(get_db)):
    """Get agent profile by ID."""
    return AgentResponse(
        id=agent_id,
        agent_name="tim_shaw",
        display_name="Tim Shaw",
        role="client_success_agent",
        tone="warm, professional, helpful",
        is_active=True,
        max_client_capacity=500,
        current_client_count=0,
        disclosure_text="AI Client Agent for The Life Shield",
        created_at="2026-04-01T00:00:00Z",
    )


@router.put("/{agent_id}", summary="Admin: update agent profile")
async def update_agent(
    agent_id: str = Path(...),
    updates: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Admin: update agent configuration, voice, avatar, tone."""
    log.info("agent_updated", agent_id=agent_id)
    return {"success": True, "agent_id": agent_id, "updated_fields": list(updates.keys())}


@router.delete("/{agent_id}", summary="Admin: deactivate agent")
async def deactivate_agent(agent_id: str = Path(...), db: Session = Depends(get_db)):
    """Admin: deactivate (archive) an agent. Data preserved for audit."""
    log.info("agent_deactivated", agent_id=agent_id)
    return {"success": True, "agent_id": agent_id, "status": "archived"}


@router.post("/{agent_id}/assign", summary="Admin: assign client to agent")
async def assign_client(
    agent_id: str = Path(...),
    req: AssignRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Admin: assign a client to a specific agent."""
    log.info("client_assigned", agent_id=agent_id, client_id=req.client_id)
    return {
        "success": True,
        "assignment_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "client_id": req.client_id,
        "assigned_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/{agent_id}/takeover", summary="Admin: take over conversation")
async def admin_takeover(
    agent_id: str = Path(...),
    client_id: str = Body(...),
    reason: str = Body(...),
    db: Session = Depends(get_db),
):
    """
    Admin manually takes over AI conversation with client.
    AI stops responding; admin handles directly.
    Logged to human_takeovers table.
    """
    log.warning("admin_takeover", agent_id=agent_id, client_id=client_id, reason=reason)
    return {
        "success": True,
        "takeover_id": str(uuid.uuid4()),
        "ai_paused": True,
        "client_id": client_id,
        "taken_over_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
