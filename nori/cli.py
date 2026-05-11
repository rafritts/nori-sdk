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


async def _run(prompt: str, model, narration: bool) -> str:
    import nori
    from nori.tools.web_search import WebSearch
    from nori.tools.api_client import ApiClient
    from nori.tools.web_client import WebClient

    nori.configure(model=model)

    from nori import Agent
    agent = Agent(
        name="cli",
        tools=[WebSearch, ApiClient, WebClient],
    )
    agent.narration = narration
    return await agent.run(prompt)


def main():
    parser = argparse.ArgumentParser(prog="nori", description="Run a Nori agent from the command line.")
    parser.add_argument("prompt", help="The prompt to send to the agent.")
    parser.add_argument("--provider", default=None, help="Provider name (e.g. xai, openai, anthropic).")
    parser.add_argument("--model", default=None, help="Model ID (e.g. grok-4.3).")
    parser.add_argument("--no-narration", action="store_true", default=False, help="Suppress agent narration.")
    args = parser.parse_args()

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

    model = _resolve_model(provider, model_id)
    result = asyncio.run(_run(args.prompt, model, not args.no_narration))
    print(result)
