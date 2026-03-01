import json
from pathlib import Path 
from typing import Any
from mybot.config.schema import Config 

def get_config_path() -> Path:
    """获取默认的配置文件路径"""
    return Path.home() / ".mybot" / "config.json"

def get_data_dir() -> Path:
    """
    获取数据目录
    """
    from mybot.utils.helpers import get_data_path
    return get_data_path()

def _migrate_config(data: dict) -> dict: 
    """迁移旧版本的配置数据到新的格式"""
    # 这里可以添加具体的迁移逻辑，例如重命名字段、调整结构等
    # 目前假设没有需要迁移的字段，直接返回原数据
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrict_to_workspace" not in tools:
        tools["restrict_to_workspace"] = exec_cfg.pop("restrictToWorkspace")
    return data

def convert_to_camel(data: Any) -> Any:
    """递归地将字典中的 snake_case 键转换为 camelCase"""
    if isinstance(data, dict):
        return {snake_to_camel(k): convert_to_camel(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_to_camel(item) for item in data]
    return data

def camel_to_snake(name: str) -> str: 
    """将 camelCase 转换为 snake_case"""
    result = [] 
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append('_')
        result.append(char.lower())
    return ''.join(result)

def snake_to_camel(name: str) -> str:
    """将 snake_case 转换为 camelCase"""
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def convert_keys(data: Any) -> Any:
    """递归地将字典中的 camelCase 键转换为 snake_case"""
    if isinstance(data, dict):
        return {camel_to_snake(k): convert_keys(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_keys(item) for item in data]
    return data

def load_config(config_path: Path | None = None) -> Config:
    """加载配置文件"""
    path = config_path or get_config_path()
    
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)

            data = _migrate_config(data)
            return Config.model_validate(convert_keys(data))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"加载配置文件失败: {e}")
    
    return Config()

def save_config(config: Config, config_path: Path | None = None) -> None:
    """保存配置文件"""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = config.model_dump()
    data = convert_to_camel(data)

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
