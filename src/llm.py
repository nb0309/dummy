"""Azure OpenAI wiring.

Ported from the legacy ``testing.py`` so the modular pipeline shares the exact
same credential handling and structured-output setup.
"""

from langchain_openai import AzureChatOpenAI

from .config import _env
from .schema import Prediction


def load_llm() -> AzureChatOpenAI:
    """Build an ``AzureChatOpenAI`` client from the environment."""
    azure_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    azure_model = _env("AZURE_MODEL", "gpt-5")
    azure_api_version = _env("AZURE_API_VERSION", "2024-02-01")
    azure_api_key = _env("AZURE_API_KEY") or _env("openai")

    if not azure_endpoint:
        raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT environment variable.")
    if not azure_api_version:
        raise RuntimeError("Missing AZURE_API_VERSION environment variable.")
    if not azure_api_key:
        raise RuntimeError("Missing AZURE_API_KEY environment variable.")

    return AzureChatOpenAI(
        azure_endpoint=azure_endpoint,
        model=azure_model,
        api_version=azure_api_version,
        api_key=azure_api_key,
    )


def load_structured_llm():
    """Return an LLM configured to emit the :class:`Prediction` schema."""
    llm = load_llm()
    return llm.with_structured_output(Prediction, method="function_calling")
