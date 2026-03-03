from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field

class AgentDefaults(BaseModel):
    """Default settings for agents."""
    workspace: str = "~/.mybot/workspace"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 8192
    max_tool_iterations: int = 20

class AgentsConfig(BaseModel):
    """Agent configuration."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)

class EmailConfig(BaseModel):
    """Email configuration."""
    enabled: bool = False 
    consent_granted: bool = False 

    #IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993 
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    #SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    #Behavior 
    auto_reply_enabled: bool = True 
    poll_interval_seconds: int = 10
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "[MyBot] Re: "
    allow_from: list[str] = Field(default_factory=list)

class ChannelsConfig(BaseModel):
    """Channel configuration."""
    email: EmailConfig = Field(default_factory=EmailConfig)
    
class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    api_key: str = ""
    api_base: str | None = None  
    extra_headers: dict[str, str] | None = None 

class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)

class GatewayConfig (BaseModel):
    """Configuration for the gateway."""
    host: str = "0.0.0.0"
    port: int = 18790

class WebSearchConfig(BaseModel):
    """Configuration for web search tools."""
    engine: str = "duckduckgo"
    api_key: str = ""
    max_results: int = 5

class WebToolsConfig(BaseModel):
    """Configuration for web tools."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)

class ExecToolConfig(BaseModel):
    """Configuration for exec tools."""
    timeout: int = 60

class ToolsConfig(BaseModel):
    """Configuration for tools."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False

class Config(BaseSettings): 
    """Root configuration for mybot."""
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property 
    def workspace_path(self) -> Path: 
        """解析工作空间路径，支持 ~ 符号"""
        return Path(self.agents.defaults.workspace).expanduser()
    
    def _match_provider(self, model: str | None = None) -> tuple["ProviderConfig | None", str | None]:
        """
        Match provider config and its registry name. Returns (config, spec_name).
        """
        from mybot.providers.registry import PROVIDERS 
        model_lower = (model or self.agents.defaults.model).lower()

        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(kw in model_lower for kw in spec.keywords) and p.api_key:
                return p, spec.name 
        
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name 
            
        return None, None 


    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """
        get_provider 的 Docstring
        
        :param self: 说明
        :param model: 说明
        :type model: str | None
        :return: 说明
        :rtype: ProviderConfig | None
        """
        p, _ = self._match_provider(model)
        return p
    
    def get_api_base(self, model: str | None = None) -> str | None:
        """
        Get API base URL for the giben model. APplies default URLs for known gateways.
        """
        from mybot.providers.registry import find_by_name
        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base 
        
        if name:
            spec = find_by_name(name) 
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        
        return None 
    
    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name