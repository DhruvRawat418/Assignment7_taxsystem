"""OpenAI connector for the adversarial reviewer."""

import os

from openai import AsyncOpenAI

from src.agents.adversarial_contract import ReviewReport


async def openai_review_call(messages):
    model = os.getenv("SILVERFILE_REVIEW_MODEL", "gpt-4.1-mini")

    async with AsyncOpenAI(
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

    return response.output_parsed.model_dump(mode="json")