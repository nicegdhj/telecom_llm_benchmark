import urllib
from typing import Dict, Optional, Union

from ais_bench.benchmark.registry import MODELS
from ais_bench.benchmark.utils.prompt import PromptList
from ais_bench.benchmark.models import BaseAPIModel, APITemplateParser
from ais_bench.benchmark.models.output import RequestOutput, Output
from ais_bench.benchmark.openicl.icl_inferencer.output_handler.ppl_inferencer_output_handler import PPLRequestOutput
import os
PromptType = Union[PromptList, str]

# Role mapping for converting internal role names to API role names
ROLE_MAP = {
    "HUMAN": "user",
    "BOT": "assistant",
    "SYSTEM": "system",
    "TOOL": "tool",
}


@MODELS.register_module()
class BailianAPI(BaseAPIModel):
    """Alibaba Bailian (百炼) API model wrapper.
    
    Bailian uses OpenAI-compatible API format with base URL:
    https://dashscope.aliyuncs.com/compatible-mode/v1
    
    Args:
        path (str): Model path or identifier (not used for API models).
        model (str): Model name (e.g., "qwen-plus", "qwen-turbo", "qwen-max").
        stream (bool): Whether to enable streaming output. Defaults to False.
        max_out_len (int): Maximum output length. Defaults to 4096.
        retry (int): Number of retry attempts. Defaults to 2.
        api_key (str): Bailian API key (DASHSCOPE_API_KEY).
        url (str): Custom API endpoint URL. If not provided, uses default Bailian endpoint.
        generation_kwargs (Dict): Additional generation parameters (temperature, top_p, etc.).
        meta_template (Dict): Meta template configuration for conversation format.
        enable_ssl (bool): Whether to enable SSL. Defaults to True for Bailian.
        verbose (bool): Whether to enable verbose logging. Defaults to False.
    """
    is_api: bool = True
    is_chat_api: bool = True

    def __init__(
        self,
        path: str = "",
        model: str = "qwen-plus",
        stream: bool = False,
        max_out_len: int = 4096,
        retry: int = 2,
        api_key: str = "",
        host_ip: str = "",
        host_port: int = 443,
        url: str = "",
        trust_remote_code: bool = False,
        generation_kwargs: Optional[Dict] = None,
        meta_template: Optional[Dict] = None,
        enable_ssl: bool = True,
        verbose: bool = False,
    ):
        # Set default URL if not provided
        if not url:
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        
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
        
        # Set API key in headers
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
            self.logger.info("Bailian API key is set")
        
        # Set default meta template for chat format
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
        
        self.model = model
        self.url = self._get_url()
        self.template_parser = APITemplateParser(self.meta_template)
        self.session = None

    def _get_url(self) -> str:
        """Get the API endpoint URL."""
        url = self.base_url
        self.logger.debug(f"Bailian API URL: {url}")
        return url

    async def get_request_body(
        self, input: PromptType, max_out_len: int, output: RequestOutput, **args
    ):
        """Construct request body for Bailian API.
        
        Args:
            input: Input prompt (string or PromptList)
            max_out_len: Maximum output length
            output: RequestOutput object to store input
            **args: Additional arguments
            
        Returns:
            dict: Request body for the API call
        """
        if max_out_len <= 0:
            return ""
        
        # Convert input to messages format
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        else:
            messages = []
            for item in input:
                msg = {"content": item["prompt"]}
                # Use role mapping
                role = item.get("role", "")
                msg["role"] = ROLE_MAP.get(role, role)
                # Copy other fields
                for key, value in item.items():
                    if key not in ["role", "prompt"]:
                        msg[key] = value
                messages.append(msg)
        
        output.input = messages
        
        # Construct request body
        request_body = dict(
            model=self.model,
            messages=messages,
        )
        
        # Add max_tokens if specified
        if max_out_len > 0:
            request_body["max_tokens"] = max_out_len
        
        # Add generation parameters
        standard_params = {"temperature", "top_p", "top_k", "presence_penalty", "frequency_penalty"}
        # Internal-only params that should NOT be forwarded to the API
        internal_params = {"ignore_eos"}
        all_params = {}
        if self.generation_kwargs:
            all_params.update(self.generation_kwargs)
        if args:
            all_params.update(args)
        
        for param in standard_params:
            if param in all_params:
                request_body[param] = all_params[param]
        
        # Pass through non-standard extra params (e.g. enable_thinking for qwen3 reasoning models)
        for param, value in all_params.items():
            if param not in standard_params and param not in internal_params:
                request_body[param] = value
        
        # Add stream parameter
        if self.stream:
            request_body["stream"] = True
        
        return request_body

    async def parse_stream_response(self, json_content, output):
        """Parse streaming response from Bailian API.
        
        Args:
            json_content: JSON response chunk
            output: Output object to update
        """
        for item in json_content.get("choices", []):
            delta = item.get("delta", {})
            if delta.get("content"):
                output.content += delta["content"]
        
        # Update token usage if available
        if json_content.get("usage"):
            output.output_tokens = json_content["usage"].get("completion_tokens", 0)

    async def parse_text_response(self, json_content, output):
        """Parse non-streaming response from Bailian API.
        
        Args:
            json_content: JSON response
            output: Output object to update
        """
        for item in json_content.get("choices", []):
            message = item.get("message", {})
            if content := message.get("content"):
                output.content += content
        
        # Update token usage
        if json_content.get("usage"):
            output.output_tokens = json_content["usage"].get("completion_tokens", 0)
            output.input_tokens = json_content["usage"].get("prompt_tokens", 0)
        
        output.update_extra_details_data_from_text_response(json_content)
        self.logger.debug(f"Output content: {output.content}")

    async def get_ppl_request_body(self, input_data: PromptType, max_out_len: int, output: PPLRequestOutput, **args):
        """Construct request body for perplexity calculation.
        
        Note: This requires the API to support logprobs parameter.
        """
        request_body = await self.get_request_body(input_data, max_out_len, output, **args)
        # Add logprobs parameter if supported by Bailian
        request_body.update({"logprobs": True, "top_logprobs": 1})
        return request_body

    def get_prompt_logprobs(self, data: dict):
        """Extract prompt logprobs from response.
        
        Args:
            data: Response data
            
        Returns:
            list: Prompt logprobs
        """
        # Extract logprobs from response if available
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("logprobs", {}).get("content", [])
        return []
