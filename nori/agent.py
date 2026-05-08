from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from nori.context import ContextFile, ContextRole


class Agent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str = "",
        api_key: str = None,
        base_url: str = None,
        context_files: list[ContextFile] = None,
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self._context_files = context_files or []
        self._api_key = api_key
        self._base_url = base_url
        self.__client: AsyncOpenAI | None = None

    @property
    def _client(self) -> AsyncOpenAI:
        if self.__client is None:
            self.__client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self.__client

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

    async def _complete(self, history: list[dict]) -> ChatCompletionMessage:
        messages = self._build_messages(history)
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message
