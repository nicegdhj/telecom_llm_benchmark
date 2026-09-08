import asyncio
import unittest

from ais_bench.benchmark.models import MaaSAPI
from ais_bench.benchmark.models.output import RequestOutput
from ais_bench.benchmark.utils.prompt import PromptList


class TestMaaSAPI(unittest.TestCase):
    def test_get_request_body_preserves_roles_and_top_level_tools(self):
        model = MaaSAPI(
            model="test-model",
            url="https://example.com/v1/chat/completions",
            generation_kwargs={"temperature": 0.01},
        )
        output = RequestOutput()
        prompts = PromptList([
            {"role": "SYSTEM", "prompt": "You are a weather assistant."},
            {"role": "HUMAN", "prompt": "What is Beijing's weather?"},
        ])
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather by city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]

        request_body = asyncio.run(
            model.get_request_body(prompts, 1024, output, tools=tools)
        )

        self.assertEqual(
            request_body["messages"],
            [
                {"role": "system", "content": "You are a weather assistant."},
                {"role": "user", "content": "What is Beijing's weather?"},
            ],
        )
        self.assertEqual(request_body["tools"], tools)
        self.assertEqual(output.input, request_body["messages"])


if __name__ == "__main__":
    unittest.main()
