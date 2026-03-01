from pathlib import Path 
from mybot.utils.helpers import ensure_dir

BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"

class SkillsLoader:
    """
    SkillLoader 的 Docstring
    """
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace 
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        ensure_dir(self.workspace_skills) 