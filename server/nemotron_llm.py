"""vLLM-compatible OpenAI LLM service for NVIDIA Nemotron."""

import os

from pipecat.services.openai.base_llm import OpenAILLMSettings
from pipecat.services.openai.llm import OpenAILLMService


class NemotronLLMService(OpenAILLMService):
    """Wraps vLLM's OpenAI-compatible endpoint for NVIDIA Nemotron."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str = "not-needed",
        **kwargs,
    ):
        # Thinking mode: enable_thinking must be passed as extra_body per-request via the
        # vLLM OpenAI-compatible API. Pipecat's OpenAILLMSettings.extra does not map to
        # extra_body — leave thinking off (default) unless the vLLM server has
        # --reasoning-parser nemotron_v3, otherwise CoT tokens get spoken aloud.
        super().__init__(
            base_url=base_url or os.environ["NEMOTRON_LLM_URL"],
            api_key=api_key,
            settings=OpenAILLMSettings(
                model=model or os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super"),
            ),
            **kwargs,
        )
