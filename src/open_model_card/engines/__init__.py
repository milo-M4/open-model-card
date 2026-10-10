"""Engine adapters.

Each engine that Open-Model-Card can talk to is one adapter file in this
package. The adapter's job is to translate the engine's HTTP API into the
shape the rest of the app expects.

Adapter contract:

    class EngineAdapter:
        name: str                            # human-readable, "llama.cpp"
        family: str                          # canonical id, "llamacpp"

        def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult
        def list_models(self, url, key, timeout=15.0) -> list[ModelInfo]
        def model_size(self, url, model_id, key, timeout=10.0) -> int | None
        def unload(self, url, model_id, key, timeout=60.0) -> UnloadResult
        def is_loaded(self, url, model_id, key, timeout=5.0) -> bool

Engines register themselves in REGISTRY below. Discovery imports this
module and iterates REGISTRY to find which engines to probe.

Adding a new engine: drop a new file in this package, implement the
adapter contract, and add it to REGISTRY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProbeResult:
    """The result of asking an engine "are you there, and how do I talk to you?"."""

    reachable: bool
    needs_auth: bool = False
    version: str | None = None
    detail: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """One model the engine can serve."""

    id: str
    size_bytes: int | None = None
    state: str | None = None  # "loaded" / "loading" / "unloaded" / None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnloadResult:
    """Result of asking the engine to unload a model."""

    attempted: bool
    unloaded: bool
    detail: str = ""


class EngineAdapter:
    """Base class. Subclasses set `name` and `family`, and implement the methods."""

    name: str = ""
    family: str = ""

    def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult:
        raise NotImplementedError

    def list_models(self, url: str, key: str | None, timeout: float = 15.0) -> list[ModelInfo]:
        raise NotImplementedError

    def model_size(self, url: str, model_id: str, key: str | None, timeout: float = 10.0) -> int | None:
        return None

    def unload(self, url: str, model_id: str, key: str | None, timeout: float = 60.0) -> UnloadResult:
        return UnloadResult(attempted=False, unloaded=False, detail="not supported")

    def is_loaded(self, url: str, model_id: str, key: str | None, timeout: float = 5.0) -> bool:
        return False


# Registry — every adapter adds itself here.
REGISTRY: dict[str, EngineAdapter] = {}


def register(adapter: EngineAdapter) -> None:
    REGISTRY[adapter.family] = adapter


def get(family: str) -> EngineAdapter | None:
    return REGISTRY.get(family)


def all_families() -> list[str]:
    return list(REGISTRY.keys())


# Import adapters so they register themselves on package import.
def _load_adapters() -> None:
    from open_model_card.engines import llamacpp, ollama, omlx, lmstudio

    register(llamacpp.LlamaCppAdapter())
    register(ollama.OllamaAdapter())
    register(omlx.OMLXAdapter())
    register(lmstudio.LMStudioAdapter())


_load_adapters()
