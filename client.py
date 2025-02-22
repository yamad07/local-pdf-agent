import os
import anthropic
from typing import cast


class AnthropicClient:
    """Singleton class for Anthropic client"""
    _instance = None
    _client: anthropic.Anthropic | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AnthropicClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @property
    def client(self) -> anthropic.Anthropic:
        return cast(anthropic.Anthropic, self._client)


# Initialize the global client
anthropic_client = AnthropicClient()
