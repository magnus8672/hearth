"""Small adapters keep upstream routing and extraction outside authorization policy."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hearth.contracts import Locality
from hearth.policy import PolicyDenied


@dataclass(frozen=True)
class Candidate:
    deployment_id: UUID
    capability: str
    healthy_until: datetime
    context_tokens: int
    quality_score: float
    queued_jobs: int
    resident: bool = True


class InferenceAdapter(Protocol):
    async def generate(self, deployment_id: UUID, messages: list[dict], *, deadline: datetime) -> dict: ...
    async def stop(self, attempt_id: UUID) -> None: ...


class StorageAdapter(Protocol):
    async def fetch(self, digest: str, *, node_id: UUID, offset: int, maximum_bytes: int) -> bytes: ...


class ToolAdapter(Protocol):
    async def invoke(self, invocation_id: UUID, tool_id: str, arguments: dict, grant_id: UUID) -> dict: ...


class KnowledgeAdapter(Protocol):
    async def index_partition(self, partition_id: UUID, source_generation: int) -> dict: ...


class CloudAdapter(Protocol):
    async def generate(self, reservation_id: UUID, payload: dict, locality: Locality) -> dict: ...


class _SelectionOnlyClient:
    """Switchyard 0.2 calls target clients; these return a route receipt without inference/egress."""
    def __init__(self, name: str):
        self.name = name

    async def call(self, request):
        return {"model": self.name, "outputs": []}


class SwitchyardRouter:
    async def select(self, candidates: list[Candidate], *, permitted_ids: set[UUID], capability: str,
                     required_context: int, now: datetime) -> UUID:
        eligible = [c for c in candidates if c.deployment_id in permitted_ids and c.capability == capability
                    and c.healthy_until > now and c.context_tokens >= required_context and c.resident]
        if not eligible:
            raise PolicyDenied("no_eligible_deployment")
        # Quality and queue eligibility belong to Hearth. Random selection only resolves equivalent choices.
        rank = max((c.quality_score, -c.queued_jobs) for c in eligible)
        finalists = sorted((c for c in eligible if (c.quality_score, -c.queued_jobs) == rank), key=lambda c: str(c.deployment_id))
        chosen = finalists[0].deployment_id
        try:
            from switchyard.libsy import LlmTarget, algorithms
            targets = [LlmTarget(str(c.deployment_id), _SelectionOnlyClient(str(c.deployment_id))) for c in finalists]
            _, receipt = await algorithms.random(targets).run({"messages": []})
            chosen = UUID(receipt["model"])
        except Exception:
            # Keep the same filtered set when an optional selector fails.
            chosen = finalists[0].deployment_id
        if chosen not in {candidate.deployment_id for candidate in finalists}:
            raise PolicyDenied("router_returned_ineligible_deployment")
        return chosen


def graphify_structural_probe(source: Path) -> dict:
    """P0 feasibility only: deterministic AST extraction, not semantic memory readiness."""
    from graphify.build import build_from_json
    from graphify.extract import extract_python
    extraction = extract_python(source)
    if extraction.get("error"):
        raise RuntimeError(extraction["error"])
    allowed_nodes = {node["id"] for node in extraction["nodes"] if node.get("source_file") == str(source)}
    extraction["nodes"] = [node for node in extraction["nodes"] if node["id"] in allowed_nodes]
    extraction["edges"] = [edge for edge in extraction["edges"]
                           if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
                           and edge.get("source_file") == str(source)]
    graph = build_from_json(extraction)
    return {"node_count": graph.number_of_nodes(), "edge_count": graph.number_of_edges(), "extraction": extraction}
