from fastapi import APIRouter, Depends

from apps.api.dependencies import get_compliance_agent
from core.models import ChatRequest
from llm.agent import ComplianceAgent

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(req: ChatRequest, agent: ComplianceAgent = Depends(get_compliance_agent)):
    answer = await agent.answer(req.message)
    return {"answer": answer}
