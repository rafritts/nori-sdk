import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _resolve_model(provider_str: str, model_str: str):
    from nori.model import Model
    from nori.providers import Provider

    try:
        provider = Provider[provider_str.upper()]
    except KeyError:
        valid = ", ".join(p.name.lower() for p in Provider)
        print(f"Error: unknown provider '{provider_str}'. Valid options: {valid}", file=sys.stderr)
        sys.exit(1)

    return Model(id=model_str, provider=provider)


def _make_agent(model, narration: bool, sandbox: bool):
    import nori
    from nori.tools._sandbox import sandbox_dir as _sandbox_dir
    from nori.tools.api_client import ApiClient
    from nori.tools.bash import Bash
    from nori.tools.browser import BrowserAgent, BrowserClient
    from nori.tools.code_runner import CodeRunner
    from nori.tools.file_edit import FileEdit
    from nori.tools.file_search import FileSearch
    from nori.tools.web_client import WebClient
    from nori.tools.web_search import WebSearch

    if sandbox:
        _sandbox_dir.set(os.getcwd())

    nori.configure(model=model)

    from nori import Agent
    agent = Agent(
        name="cli",
        tools=[ApiClient, Bash, BrowserAgent, BrowserClient, CodeRunner, FileEdit, FileSearch, WebClient, WebSearch],
    )
    agent.narration = narration
    return agent


async def _spin_while(coro):
    frames = ["/", "|", "\\", "—"]
    done = asyncio.Event()

    async def spin():
        i = 0
        while not done.is_set():
            sys.stdout.write(f"\r[{frames[i % len(frames)]}] ")
            sys.stdout.flush()
            i += 1
            await asyncio.sleep(0.1)
        sys.stdout.write("\r    \r")
        sys.stdout.flush()

    spin_task = asyncio.create_task(spin())
    try:
        return await coro
    finally:
        done.set()
        await spin_task


async def _run_repl(model, narration: bool, sandbox: bool, initial_prompt: str | None):
    agent = _make_agent(model, narration, sandbox)
    prompt = initial_prompt

    while True:
        if prompt is None:
            try:
                prompt = input("\n[::] ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                break
        if not prompt or prompt.lower() in ("exit", "quit"):
            break
        try:
            result = await _spin_while(agent.run(prompt))
            print(f"\n{result}")
        except KeyboardInterrupt:
            print("\n[interrupted]")
        prompt = None


async def _run_once(model, narration: bool, sandbox: bool, prompt: str) -> str:
    agent = _make_agent(model, narration, sandbox)
    return await agent.run(prompt)


def main():
    parser = argparse.ArgumentParser(prog="nori", description="Run a Nori agent from the command line.")
    parser.add_argument("prompt", nargs="?", default=None, help="The prompt to send to the agent.")
    parser.add_argument("--provider", default=None, help="Provider name (e.g. xai, openai, anthropic).")
    parser.add_argument("--model", default=None, help="Model ID (e.g. grok-4.3).")
    parser.add_argument("--no-narration", action="store_true", default=False, help="Suppress agent narration.")
    parser.add_argument("--no-sandbox", action="store_true", default=False, help="Allow tools to access paths outside the current directory.")
    parser.add_argument("--repl", action="store_true", default=False, help="Stay in a conversation loop after each response.")
    args = parser.parse_args()

    if not args.repl and args.prompt is None:
        parser.error("prompt is required unless --repl is set")

    provider = args.provider or os.getenv("NORI_CLI_PROVIDER")
    model_id = args.model or os.getenv("NORI_CLI_MODEL")

    if not provider or not model_id:
        print(
            "Error: provider and model are required.\n"
            "Set NORI_CLI_PROVIDER and NORI_CLI_MODEL in your .env, or use --provider and --model flags.\n"
            "Example: nori --provider xai --model grok-4.3 \"your prompt\"",
            file=sys.stderr,
        )
        sys.exit(1)

    no_sandbox = args.no_sandbox or os.getenv("NORI_CLI_NO_SANDBOX", "").lower() in ("1", "true", "yes")
    model = _resolve_model(provider, model_id)

    try:
        if args.repl:
            asyncio.run(_run_repl(model, not args.no_narration, not no_sandbox, args.prompt))
        else:
            result = asyncio.run(_run_once(model, not args.no_narration, not no_sandbox, args.prompt))
            print(result)
    except KeyboardInterrupt:
        print()
        sys.exit(0)
