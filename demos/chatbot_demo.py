"""
Chatbot demo — exposes a nori Agent as an OpenAI-compatible chat server.

Run:
    uv run demos/chatbot_demo.py

Then in Open WebUI:
    Settings → Connections → Add connection
    URL: http://localhost:7732/v1
    API key: nori  (any non-empty string)
"""

from nori import Agent, serve
from nori.model import Model
from nori.tools.bash import Bash


SYSTEM_PROMPT = """\
You are a helpful assistant with access to a Bash tool for running shell commands.
When asked about the system, files, or anything that benefits from a live check, use the tool.
"""


def make_agent():
    return Agent(
        name="assistant",
        model=Model.GPT4O_MINI,
        system_prompt=SYSTEM_PROMPT,
        tools=[Bash],
        max_turns=20,
    )


serve(make_agent, port=7732)
