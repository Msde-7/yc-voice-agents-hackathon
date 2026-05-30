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
        # Thinking mode must be off for voice — without --reasoning-parser nemotron_v3
        # on the vLLM server, chain-of-thought tokens land in `content` and get spoken aloud.
        enable_thinking = os.getenv("NEMOTRON_ENABLE_THINKING", "False").lower() == "true"

        super().__init__(
            base_url=base_url or os.environ["NEMOTRON_LLM_URL"],
            api_key=api_key,
            settings=OpenAILLMSettings(
                model=model or os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super"),
                extra={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
            ),
            **kwargs,
        )
