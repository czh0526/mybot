import os 
import json 
import litellm 
from datetime import datetime
from litellm import acompletion  
from typing import Any 
from mybot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from mybot.providers.registry import find_by_model, find_gateway  
from mybot.utils.helpers import get_log_path, log_msg 

class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.
    """
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None, 
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None, 
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

        self._gateway = find_gateway(provider_name, api_key, api_base)

        if api_key:
            self._setup_env(api_key, api_base, default_model)

        if api_base:
            litellm.api_base = api_base 
        
        litellm.suppress_debug_info = True 
        litellm.drop_params = True 
        
    def _setup_env(
        self,
        api_key: str, 
        api_base: str | None,
        model: str 
    ) -> None:
        """
        Set environment variables based on detected provider.
        """
        spec = self._gateway or find_by_model(model)
        if not spec:
            return 
        
        if self._gateway:
            os.environ[spec.env_key] = api_key 
        else:
            os.environ.setdefault(spec.env_key, api_key)
        
        effective_base = api_base or spec.default_api_base 
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", api_key)
            os.environ.setdefault(env_name, resolved)


    def get_default_model(self) -> str:
        """
        Get the default model.
        """
        return self.default_model
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.
        """
        model = self._resolve_model(model or self.default_model)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        self._apply_model_overrides(model, kwargs)

        if self.api_base:
            kwargs["api_base"] = self.api_base

        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        
        if tools:
            kwargs["tools"] = tools 
            kwargs["tool_choice"] = "auto"

        try:
            # debug info
            now = datetime.now()
            curr_time_str = now.strftime("%Y%m%d%H%M%S")
            msg: str = json.dumps(kwargs, indent=True)
            log_msg(msg, get_log_path()/f"{curr_time_str}_request")

            response = await acompletion(**kwargs)
            
            # debug info 
            log_msg(f"LLM Response => {response}", get_log_path()/f"{curr_time_str}_response")

            return self._parse_response(response)
        except Exception as e:
            return LLMResponse(
                content = f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )
        
    def _parse_response(self, response: Any) -> LLMResponse:
        """
        Parse LiteLLM response into our standard format.
        """
        choice = response.choices[0]
        message = choice.message 

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments 
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}

                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def _resolve_model(self, model: str) -> str:
        """
        Resolve model name by applying provider/gateway prefixes.
        """
        if self._gateway:
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model 
        
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"

        return model 


    def _apply_model_overrides(
        self,
        model: str,
        kwargs: dict[str, Any],
    ) -> None:
        """
        Apply model-specific parameter overrides from the registry.
        """
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return 
                
    
