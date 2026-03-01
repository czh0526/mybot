
from pathlib import Path
from datetime import datetime 

def ensure_dir(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_data_path() -> Path:
    """获取数据目录路径"""
    return ensure_dir(Path.home() / ".mybot")

def get_workspace_path(workspace: str | None = None) -> Path:
    """获取工作空间路径"""
    if workspace:
        path = Path(workspace).expanduser()
    else :
        path = Path.home() / ".mybot" / "workspace"
    return ensure_dir(path)

def safe_filename(name: str) -> str:
    """
    将字符串转换为安全的文件名
    """
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()

def today_date() -> str:
    """
    Get today's date in YYYY-MM-DD format.
    """
    return datetime.now().strftime("%Y-%m-%d")

def get_log_path(data_path: Path | None = None) -> Path:
    dp = data_path or get_data_path()
    return ensure_dir(dp / "logs")

def log_msg(msg: str, log_file_name: Path):
    with open(log_file_name, 'w', encoding="utf-8") as f:
        f.write(msg)