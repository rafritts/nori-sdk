from openai import AsyncOpenAI


async def summarize(content: str, reason: str, client: AsyncOpenAI, model: str) -> str:
    prompt = (
        f"Summarize the following tool output. Focus on: {reason}\n\n"
        f"Output:\n{content}"
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or content
