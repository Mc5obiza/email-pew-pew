import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def get_llm() -> ChatOpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY (or OPENAI_API_KEY) is required to use OpenRouter."
        )

    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.4"))
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=SecretStr(api_key),
        base_url="https://openrouter.ai/api/v1",
    )
