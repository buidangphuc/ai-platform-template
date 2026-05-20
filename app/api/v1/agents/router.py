from fastapi import APIRouter, Depends, Request

from app.contracts.agents import AgentRequest, AgentResponse
from app.modules.identity.auth import require_authenticated_request

router = APIRouter(
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(require_authenticated_request)],
)


@router.post("/run", response_model=AgentResponse)
async def run_agent(payload: AgentRequest, request: Request):
    return await request.app.state.adapters.agent_runtime.run(payload)
