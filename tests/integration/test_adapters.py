from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hearth.adapters import Candidate, SwitchyardRouter, _SelectionOnlyClient, graphify_structural_probe
from hearth.policy import PolicyDenied


async def test_real_switchyard_respects_filtered_candidates(monkeypatch):
    calls = []
    original = _SelectionOnlyClient.call

    async def observed_call(self, request):
        calls.append(self.name)
        return await original(self, request)

    monkeypatch.setattr(_SelectionOnlyClient, "call", observed_call)
    now = datetime.now(UTC)
    first, second, forbidden = uuid4(), uuid4(), uuid4()
    candidates = [Candidate(id, "chat.general", now + timedelta(seconds=15), 8192, score, 0)
                  for id, score in ((first, 0.8), (second, 0.8), (forbidden, 1.0))]
    router = SwitchyardRouter()
    seen = {await router.select(candidates, permitted_ids={first, second}, capability="chat.general",
                                required_context=1024, now=now) for _ in range(20)}
    assert seen <= {first, second}
    assert seen
    assert len(calls) == 20, "The real pinned library must run, not silently use the fallback"
    assert set(calls) <= {str(first), str(second)}
    with pytest.raises(PolicyDenied, match="no_eligible_deployment"):
        await router.select(candidates, permitted_ids={first}, capability="chat.general", required_context=32768, now=now)
    with pytest.raises(PolicyDenied, match="no_eligible_deployment"):
        await router.select(candidates, permitted_ids={first}, capability="chat.general", required_context=10, now=now + timedelta(seconds=16))


def test_real_graphify_structural_extraction_without_network(tmp_path, monkeypatch):
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError("structural graph extraction must not access the network")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-canary-must-never-be-used")
    source = tmp_path / "approved_source.py"
    source.write_text("class Hearth:\n    def ready(self):\n        return True\n")
    result = graphify_structural_probe(source)
    assert result["node_count"] == 3
    assert result["edge_count"] == 2
    assert all(node["source_file"] == str(source) for node in result["extraction"]["nodes"])
