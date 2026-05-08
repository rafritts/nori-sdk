import asyncio
import json

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from nori.context import ContextFile, ContextRole
from nori.exceptions import MaxTurnsExceeded


class Agent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str = "",
        api_key: str = None,
        base_url: str = None,
        context_files: list[ContextFile] = None,
        tools: list = None,
        max_turns: int | None = 10,
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self._context_files = context_files or []
        self._api_key = api_key
        self._base_url = base_url
        self.__client: AsyncOpenAI | None = None
        self._tools: dict = {self._tool_name(t): t for t in (tools or [])}
        self._max_turns = max_turns
        self._history: list[dict] = []
        self._turn_count = 0

    @property
    def _client(self) -> AsyncOpenAI:
        if self.__client is None:
            self.__client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self.__client

    def _tool_name(self, t) -> str:
        return t.schema["function"]["name"]

    def _tool_schemas(self) -> list[dict]:
        return [t.schema for t in self._tools.values()]

    def _build_messages(self, history: list[dict]) -> list[dict]:
        system_content = self.system_prompt
        for cf in self._context_files:
            if cf.role == ContextRole.SYSTEM:
                system_content += "\n\n" + cf.content

        messages = [{"role": "system", "content": system_content}]

        for cf in self._context_files:
            if cf.role == ContextRole.USER:
                messages.append({"role": "user", "content": cf.content})
            elif cf.role == ContextRole.ASSISTANT:
                messages.append({"role": "assistant", "content": cf.content})

        messages.extend(history)
        return messages

    def _message_to_dict(self, message: ChatCompletionMessage) -> dict:
        d: dict = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        return d

    async def _invoke_tool(self, tc) -> dict:
        fn = self._tools[tc.function.name]
        args = json.loads(tc.function.arguments)
        result = await fn(**args)
        return {"role": "tool", "tool_call_id": tc.id, "content": str(result)}

    async def _execute_tools(self, tool_calls) -> list[dict]:
        return list(await asyncio.gather(*[self._invoke_tool(tc) for tc in tool_calls]))

    async def _complete(self, history: list[dict]) -> ChatCompletionMessage:
        messages = self._build_messages(history)
        kwargs: dict = {"model": self.model, "messages": messages}
        if self._tools:
            kwargs["tools"] = self._tool_schemas()
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message

    async def run(self, prompt: str) -> str:
        self._history.append({"role": "user", "content": prompt})

        while True:
            if self._max_turns is not None and self._turn_count >= self._max_turns:
                raise MaxTurnsExceeded(f"Reached max_turns={self._max_turns}")

            message = await self._complete(self._history)
            self._turn_count += 1
            self._history.append(self._message_to_dict(message))

            if not message.tool_calls:
                return message.content or ""

            tool_results = await self._execute_tools(message.tool_calls)
            self._history.extend(tool_results)
