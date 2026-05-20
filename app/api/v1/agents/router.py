from fastapi import APIRouter, Request

from app.contracts.agents import AgentRequest, AgentResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run", response_model=AgentResponse)
async def run_agent(payload: AgentRequest, request: Request):
    return await request.app.state.adapters.agent_runtime.run(payload)
