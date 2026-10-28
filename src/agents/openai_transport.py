"""OpenAI connector for the adversarial reviewer."""

import os

from openai import AsyncOpenAI

from src.agents.adversarial_contract import ReviewReport


async def _request(messages, *, api_key=None, model=None, usage_callback=None):
    model = model or os.getenv("SILVERFILE_REVIEW_MODEL", "gpt-4.1-mini")

    async with AsyncOpenAI(
        api_key=api_key,
        timeout=35.0,
        max_retries=0,
    ) as client:
        response = await client.responses.parse(
            model=model,
            input=messages,
            text_format=ReviewReport,
            max_output_tokens=3000,
            store=False,
        )

    if response.status != "completed" or response.output_parsed is None:
        raise RuntimeError("OpenAI did not return a complete review report.")
    if usage_callback is not None and response.usage is not None:
        usage_callback({'input_tokens': response.usage.input_tokens,
                        'output_tokens': response.usage.output_tokens})

    return response.output_parsed.model_dump(mode="json")


async def openai_review_call(messages):
    return await _request(messages)


def make_openai_review_call(*, api_key=None, usage_callback=None):
    """Bind a session credential without changing process globals or case state."""
    if api_key is None and usage_callback is None:
        return openai_review_call
    async def call(messages):
        return await _request(messages, api_key=api_key, usage_callback=usage_callback)
    return call
