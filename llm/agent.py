from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

from core.config import settings
from graph.exposure_service import ExposureService
from graph.redis_graph_repository import RedisGraphRepository
from observability.circuit_breakers import llm_breaker
from observability.metrics import llm_duration, llm_errors
from observability.tracing import get_tracer
from vector.retriever import RetrievalService


@dataclass
class AgentDeps:
    retrieval: RetrievalService
    graph: RedisGraphRepository
    exposure: ExposureService


_model = OpenAIModel(
    settings.primary_model,
    base_url=settings.litellm_base_url,
    api_key=settings.litellm_api_key,
)

agent = Agent(
    _model,
    deps_type=AgentDeps,
    system_prompt=(
        "You are a compliance analyst for AML, PEP, and sanctions investigations. "
        "Use the available tools to retrieve entities, check exposure, and surface "
        "relevant documents. Be concise and cite specific entity IDs where relevant."
    ),
)


@agent.tool
def search_documents(ctx: RunContext[AgentDeps], query: str) -> str:
    """Semantic + graph hybrid search over compliance documents."""
    result = ctx.deps.retrieval.search(query)
    return result.model_dump_json()


@agent.tool
def get_entity(ctx: RunContext[AgentDeps], entity_id: str) -> str:
    """Fetch the full profile for a known entity ID."""
    return str(ctx.deps.graph.get_entity_profile(entity_id))


@agent.tool
def get_exposure(ctx: RunContext[AgentDeps], entity_id: str) -> str:
    """Return PEP/sanctions exposure and related entity graph for an entity."""
    return str(ctx.deps.exposure.get_exposure(entity_id))


@agent.tool
def expand_entity(ctx: RunContext[AgentDeps], entity_name: str) -> str:
    """Resolve a name to an entity and return its 2-hop graph neighbourhood."""
    entities = ctx.deps.retrieval.resolver.extract_and_resolve(entity_name)
    if not entities:
        return "[]"
    related = ctx.deps.graph.expand_entity(entities[0].id)
    return str([e.model_dump() for e in related])


class ComplianceAgent:
    def __init__(self, deps: AgentDeps):
        self.deps = deps

    async def answer(self, question: str) -> str:
        import time
        tracer = get_tracer()
        t0 = time.time()
        with tracer.start_as_current_span("llm.agent_run") as span:
            span.set_attribute("question.length", len(question))
            try:
                result = await llm_breaker.call_async(agent.run, question, deps=self.deps)
                llm_duration.record(time.time() - t0)
                return result.data
            except Exception as exc:
                llm_errors.add(1)
                span.record_exception(exc)
                raise
