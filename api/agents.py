"""
The Life Shield - Agent Profile Routes (Admin)
GET    /agents
POST   /agents
GET    /agents/{agent_id}
PUT    /agents/{agent_id}
DELETE /agents/{agent_id}
POST   /agents/{agent_id}/assign

All agent-management endpoints require ADMIN role.
GET /agents can be accessed by ADMIN or AGENT role.
"""

import math
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from config.security import UserRole
from database import get_db
from middleware.auth import (
    get_current_verified_user,
    require_role,
    require_permission,
    log_audit,
)
from models.user import User
from models.agent import AgentProfile, ClientAgentAssignment
from schemas.agent import (
    AgentCreateRequest, AgentUpdateRequest,
    AgentResponse, AgentListResponse,
    AgentAssignRequest,
)
from schemas.common import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


# ─────────────────────────────────────────────
# GET /agents  — List all agents
# ─────────────────────────────────────────────

@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all agent profiles",
    description="Admin or Agent role required. Supports pagination and filtering by status.",
)
async def list_agents(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    role: Optional[str] = Query(None, description="Filter by agent role"),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> AgentListResponse:
    query = select(AgentProfile)

    if is_active is not None:
        query = query.where(AgentProfile.is_active == is_active)
    if role:
        query = query.where(AgentProfile.role == role)

    # Total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    # Paginated results
    offset = (page - 1) * per_page
    result = await db.execute(
        query.offset(offset).limit(per_page).order_by(AgentProfile.created_at.desc())
    )
    agents = result.scalars().all()

    return AgentListResponse(
        items=[AgentResponse.model_validate(a) for a in agents],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0,
    )


# ─────────────────────────────────────────────
# POST /agents  — Create agent
# ─────────────────────────────────────────────

@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent profile",
    description="Admin only. Creates a new AI agent persona (e.g., Tim Shaw).",
)
async def create_agent(
    payload: AgentCreateRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    # Check unique agent_name
    existing = await db.execute(
        select(AgentProfile).where(AgentProfile.agent_name == payload.agent_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent with name '{payload.agent_name}' already exists.",
        )

    # Safety: can_make_promises and can_override_decisions are ALWAYS False
    agent = AgentProfile(
        **payload.model_dump(exclude={"can_make_promises", "can_override_decisions"}),
        can_make_promises=False,
        can_override_decisions=False,
        active_since=datetime.now(timezone.utc),
    )
    db.add(agent)
    await db.flush()

    await log_audit(
        db=db,
        action="agent.created",
        resource_type="agent_profile",
        resource_id=str(agent.id),
        user_id=current_user.id,
        details=f'{{"display_name": "{agent.display_name}", "role": "{agent.role}"}}',
        ip_address=request.client.host if request.client else None,
        success=True,
    )

    logger.info(f"Agent created: {agent.display_name} ({agent.id}) by {current_user.email}")
    return AgentResponse.model_validate(agent)


# ─────────────────────────────────────────────
# GET /agents/{agent_id}  — Get single agent
# ─────────────────────────────────────────────

@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent profile",
    description="Admin or Agent role. Returns full agent profile.",
)
async def get_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return AgentResponse.model_validate(agent)


# ─────────────────────────────────────────────
# PUT /agents/{agent_id}  — Update agent
# ─────────────────────────────────────────────

@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update agent profile",
    description=(
        "Admin only. Update any agent field. "
        "can_make_promises and can_override_decisions are immutable (always False)."
    ),
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    update_data = payload.model_dump(exclude_unset=True)

    # These can never be changed via API
    update_data.pop("can_make_promises", None)
    update_data.pop("can_override_decisions", None)

    for field, value in update_data.items():
        setattr(agent, field, value)

    # Track deactivation timestamp
    if "is_active" in update_data and not update_data["is_active"]:
        agent.deactivated_at = datetime.now(timezone.utc)

    await log_audit(
        db=db,
        action="agent.updated",
        resource_type="agent_profile",
        resource_id=str(agent.id),
        user_id=current_user.id,
        details=str(update_data),
        ip_address=request.client.host if request.client else None,
        success=True,
    )

    logger.info(f"Agent updated: {agent.display_name} ({agent.id}) by {current_user.email}")
    return AgentResponse.model_validate(agent)


# ─────────────────────────────────────────────
# DELETE /agents/{agent_id}  — Deactivate agent
# ─────────────────────────────────────────────

@router.delete(
    "/{agent_id}",
    response_model=SuccessResponse,
    summary="Deactivate agent",
    description=(
        "Admin only. Soft-deletes (deactivates) an agent. "
        "Does not hard-delete to preserve audit trail."
    ),
)
async def delete_agent(
    agent_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    if not agent.is_active:
        return SuccessResponse(message="Agent is already inactive.")

    agent.is_active = False
    agent.is_accepting_clients = False
    agent.deactivated_at = datetime.now(timezone.utc)

    await log_audit(
        db=db,
        action="agent.deactivated",
        resource_type="agent_profile",
        resource_id=str(agent.id),
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        success=True,
    )

    logger.info(f"Agent deactivated: {agent.display_name} ({agent.id}) by {current_user.email}")
    return SuccessResponse(message=f"Agent '{agent.display_name}' has been deactivated.")


# ─────────────────────────────────────────────
# POST /agents/{agent_id}/assign  — Assign agent to client
# ─────────────────────────────────────────────

@router.post(
    "/{agent_id}/assign",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign agent to client",
    description="Admin only. Assigns an agent to a client user, replacing any existing active assignment.",
)
async def assign_agent_to_client(
    agent_id: uuid.UUID,
    payload: AgentAssignRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    # Verify agent exists + active
    agent_result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active agent not found.")

    # Verify client user exists
    client_result = await db.execute(
        select(User).where(User.id == payload.client_user_id, User.role == UserRole.CLIENT)
    )
    client = client_result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client user not found.")

    # Deactivate any existing assignment
    existing_result = await db.execute(
        select(ClientAgentAssignment).where(
            ClientAgentAssignment.client_user_id == payload.client_user_id,
            ClientAgentAssignment.is_active == True,
        )
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False
        existing.reassigned_at = datetime.now(timezone.utc)

    # Create new assignment
    assignment = ClientAgentAssignment(
        client_user_id=payload.client_user_id,
        agent_id=agent_id,
        assigned_by_user_id=current_user.id,
        notes=payload.notes,
        is_active=True,
    )
    db.add(assignment)

    await log_audit(
        db=db,
        action="agent.assigned",
        resource_type="client_agent_assignment",
        resource_id=str(assignment.id) if assignment.id else None,
        user_id=current_user.id,
        details=f'{{"agent_id": "{agent_id}", "client_user_id": "{payload.client_user_id}"}}',
        ip_address=request.client.host if request.client else None,
        success=True,
    )

    return SuccessResponse(
        message=f"Agent '{agent.display_name}' assigned to client '{client.full_name}'."
    )
