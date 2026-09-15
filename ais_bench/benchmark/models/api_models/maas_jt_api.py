import urllib
from typing import Dict, Optional, Union

from ais_bench.benchmark.registry import MODELS
from ais_bench.benchmark.utils.prompt import PromptList
from ais_bench.benchmark.models import BaseAPIModel, APITemplateParser
from ais_bench.benchmark.models.output import RequestOutput, Output
from ais_bench.benchmark.openicl.icl_inferencer.output_handler.ppl_inferencer_output_handler import PPLRequestOutput

PromptType = Union[PromptList, str]

# Role mapping for converting internal role names to API role names
ROLE_MAP = {
    "HUMAN": "user",
    "BOT": "assistant",
    "SYSTEM": "system",
    "TOOL": "tool",
}


@MODELS.register_module()
class MaaSJTAPI(BaseAPIModel):
    is_api: bool = True
    is_chat_api: bool = True

    def __init__(
        self,
        path: str = "",
        model: str = "",
        stream: bool = False,
        max_out_len: int = 4096,
        retry: int = 2,
        api_key: str = "",
        host_ip: str = "localhost",
        host_port: int = 8080,
        url: str = "",
        trust_remote_code: bool = False,
        generation_kwargs: Optional[Dict] = None,
        meta_template: Optional[Dict] = None,
        enable_ssl: bool = False,
        verbose: bool = False,
    ):
        super().__init__(
            path=path,
            stream=stream,
            max_out_len=max_out_len,
            retry=retry,
            api_key=api_key,
            host_ip=host_ip,
            host_port=host_port,
            url=url,
            generation_kwargs=generation_kwargs,
            meta_template=meta_template,
            enable_ssl=enable_ssl,
            verbose=verbose,
        )
        if api_key:
            if not api_key.startswith("Bearer "):
                self.headers["Authorization"] = f"Bearer {api_key}"
            else:
                self.headers["Authorization"] = api_key
            self.logger.info("API key is set")
        self.headers["Content-Type"] = "application/json"
        self.meta_template = (
            dict(
                round=[
                    dict(role="HUMAN", api_role="HUMAN"),
                    dict(role="BOT", api_role="BOT", generate=True),
                ],
                reserved_roles=[dict(role="SYSTEM", api_role="SYSTEM")],
            )
            if not meta_template
            else meta_template
        )
        self.model = model if model else self._get_service_model_path()
        self.url = url if url and "chat/completions" in url else self._get_url()
        self.template_parser = APITemplateParser(self.meta_template)
        self.session = None

    def _get_url(self) -> str:
        endpoint = "v1/chat/completions"
        url = urllib.parse.urljoin(self.base_url, endpoint)
        self.logger.debug(f"Request url: {url}")
        return url

    async def get_request_body(
        self, input: PromptType, max_out_len: int, output: RequestOutput, **args
    ):
        if max_out_len <= 0:
            return ""
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        else:
            messages = []
            for item in input:
                msg = {"content": item["prompt"]}
                # Use hash table (dict) driven approach for role mapping
                role = item.get("role", "")
                msg["role"] = ROLE_MAP.get(role, role)  # Use original role if not in map
                for key, value in item.items(): # copy all other items to msg
                    if key not in ["role", "prompt"]:
                        msg[key] = value
                messages.append(msg)
        output.input = messages
        request_body = dict(
            model=self.model,
            stream=self.stream,
            messages=messages,
        )
        standard_params = {"temperature", "top_p"}
        all_params = {}
        if self.generation_kwargs:
            all_params.update(self.generation_kwargs)
        if args:
            all_params.update(args)
        for param in standard_params:
            if param in all_params:
                request_body[param] = all_params[param]
        if self.stream:
            request_body["stream"] = True
        return request_body

    async def parse_stream_response(self, json_content, output):
        if "error" in json_content:
            output.content = f"API Error: {json_content['error']}"
            output.success = False
            return
        for item in json_content.get("choices", []):
            if item["delta"].get("content"):
                output.content += item["delta"]["content"]
            if item["delta"].get("reasoning_content"):
                output.reasoning_content += item["delta"]["reasoning_content"]
        if json_content.get("usage"):
            output.output_tokens = json_content["usage"]["completion_tokens"]

    async def parse_text_response(self, json_content, output):
        if "error" in json_content:
            output.content = f"API Error: {json_content['error']}"
            output.success = False
            return
        for item in json_content.get("choices", []):
            if content:=item["message"].get("content"):
                output.content += content
            if reasoning_content:=item["message"].get("reasoning_content"):
                output.reasoning_content += reasoning_content
        if json_content.get("usage"):
            output.output_tokens = json_content["usage"]["completion_tokens"]
        output.update_extra_details_data_from_text_response(json_content)
        self.logger.debug(f"Output content: {output.content}")
        self.logger.debug(f"Output reasoning content: {output.reasoning_content}")

    async def get_ppl_request_body(self, input_data:PromptType, max_out_len: int, output: PPLRequestOutput, **args):
        request_body = await self.get_request_body(input_data, max_out_len, output, **args)
        request_body.update({"prompt_logprobs": 0})
        return request_body

    def get_prompt_logprobs(self, data: dict):
        return data.get("prompt_logprobs", [])



