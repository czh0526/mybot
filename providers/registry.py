from typing import Any 
from dataclasses import dataclass 

@dataclass(frozen=True)
class ProviderSpec:
    """
    ProviderSpec 的 Docstring
    """
    name: str
    keywords: tuple[str, ...]
    env_key: str 
    display_name: str = ""

    litellm_prefix: str = ""
    skip_prefixes: tuple[str, ...] = ()

    env_extras: tuple[tuple[str, str], ...] = ()

    is_gateway: bool = False 
    is_local: bool = False 
    detect_by_key_prefix: str = ""
    detect_by_base_keyword: str = ""
    default_api_base: str = ""

    strip_model_prefix: bool = False 
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    @property 
    def label(self) -> str:
        return self.display_name or self.name.title()
    

PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        litellm_prefix="openrouter",
        skip_prefixes=(),
        env_extras=(),
        is_gateway=True,
        is_local=False,
        detect_by_key_prefix="sk-or-",
        detect_by_base_keyword="openrouter",
        default_api_base="https://openrouter.ai/api/v1",
        strip_model_prefix=False,
        model_overrides=(),
    ), 
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        env_key="DEEPSEEK_API_KEY",
        display_name="DeepSeek",
        litellm_prefix="deepseek",
        skip_prefixes=("deepseek/",),
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
    )
)

def find_gateway(
    provider_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> ProviderSpec | None:
    """
    Detect gateway/local provider.
    """
    if provider_name:
        spec = find_by_name(provider_name)
        if spec and (spec.is_gateway or spec.is_local):
            return spec 
        
    for spec in PROVIDERS:
        if spec.detect_by_key_prefix and api_key and api_key.startswith(spec.detect_by_key_prefix):
            return spec 
        if spec.detect_by_base_keyword and api_base and spec.detect_by_base_keyword in api_base:
            return spec 
        
    return None 

def find_by_name(name: str) -> ProviderSpec | None:
    """
    Find a provider spec by config field name, e.g. "dashscope".
    """
    for spec in PROVIDERS:
        if spec.name == name:
            return spec 
    return None 

def find_by_model(model: str) -> ProviderSpec | None:
    """
    Match a standard provider by model-name keyword (case-insensitive).
    """
    model_lower = model.lower()
    for spec in PROVIDERS:
        if spec.is_gateway or spec.is_local:
            continue
        if any(kw in model_lower for kw in spec.keywords):
            return spec
    return None 