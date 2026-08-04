async def summarize(content: str, reason: str, completer, model: str) -> str:
    prompt = (
        f"Summarize the following tool output. Focus on: {reason}\n\n"
        f"Output:\n{content}"
    )
    result = await completer.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return result.message.content or content
