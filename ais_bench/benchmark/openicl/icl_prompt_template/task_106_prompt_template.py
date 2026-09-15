from typing import Dict, Hashable, Optional

from ais_bench.benchmark.registry import ICL_PROMPT_TEMPLATES
from ais_bench.benchmark.openicl.icl_prompt_template.icl_prompt_template_base import (
    BasePromptTemplate,
    PromptType,
)
from ais_bench.benchmark.utils.prompt import PromptList


@ICL_PROMPT_TEMPLATES.register_module()
class Task106PromptTemplate(BasePromptTemplate):
    """Render user turns as separate HUMAN messages with API parser sections."""

    def generate_item(
        self,
        entry: Dict,
        output_field: Optional[Hashable] = None,
        output_field_replace_token: Optional[str] = "",
        ice_field_replace_token: Optional[str] = "",
    ) -> PromptType:
        prompt = PromptList()
        prompt.append({"section": "begin", "pos": "begin"})
        prompt.append({
            "role": "SYSTEM",
            "fallback_role": "HUMAN",
            "prompt": self.template,
        })
        prompt.append({"section": "begin", "pos": "end"})
        prompt.append({"section": "round", "pos": "begin"})
        for message in entry["input"]:
            if isinstance(message, dict):
                prompt.append({**message, "_preserve_role_boundary": True})
            else:
                prompt.append({
                    "role": "HUMAN",
                    "prompt": message,
                    "_preserve_role_boundary": True,
                })
        prompt.append({"role": "BOT", "prompt": output_field_replace_token})
        prompt.append({"section": "round", "pos": "end"})
        return prompt
