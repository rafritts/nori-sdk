import asyncio


async def map(agent, items: list[str], *, concurrency: int | None = None) -> list[str]:
    """Run agent on each item in parallel, collecting results in input order.

    Each item runs on a fresh clone of the agent — parallel runs never share
    history, traces, or token counts. The agent passed in is left untouched.

    Args:
        agent: A Nori Agent instance, used as the template for each run.
        items: Prompts to run the agent against.
        concurrency: Max simultaneous runs. Unbounded if None.
    """
    sem = asyncio.Semaphore(concurrency) if concurrency is not None else None

    async def run_one(item: str) -> str:
        sub = agent._clone()
        if sem is not None:
            async with sem:
                return await sub.run(item)
        return await sub.run(item)

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(run_one(item)) for item in items]

    return [t.result() for t in tasks]


async def pipeline(agents: list, items: list[str] | str) -> list[str] | str:
    """Chain agents so each agent's output feeds the next.

    Stages run concurrently — stage N+1 starts processing as soon as stage N
    emits its first result (CSP / producer-consumer via asyncio.Queue).

    Args:
        agents: Ordered list of Agent instances forming the pipeline.
        items: A single prompt string or a list of prompt strings.

    Returns:
        A single result string when items is a string, otherwise a list.
    """
    single = isinstance(items, str)
    inputs: list[str] = [items] if single else list(items)

    # One queue between each pair of adjacent stages, plus input and output queues.
    queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(len(agents) + 1)]

    for item in inputs:
        await queues[0].put(item)
    await queues[0].put(None)  # sentinel marks end of stream

    async def stage(agent, in_q: asyncio.Queue, out_q: asyncio.Queue) -> None:
        while True:
            item = await in_q.get()
            if item is None:
                await out_q.put(None)
                return
            result = await agent.run(item)
            await out_q.put(result)

    async with asyncio.TaskGroup() as tg:
        for i, agent in enumerate(agents):
            tg.create_task(stage(agent, queues[i], queues[i + 1]))

    results: list[str] = []
    while True:
        item = await queues[-1].get()
        if item is None:
            break
        results.append(item)

    return results[0] if single else results
