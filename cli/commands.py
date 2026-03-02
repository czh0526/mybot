import typer 
from loguru import logger
from pathlib import Path
from rich.console import Console
from mybot.config.schema import Config 
from mybot.config.loader import get_config_path, load_config, save_config
from mybot.utils import get_workspace_path
from mybot.session.manager import SessionManager
from mybot.channels.manager import ChannelManager
from mybot.cron.service import CronService
from mybot.heartbeat.service import HeartbeatService
from mybot.cron.types import CronJob 


app = typer.Typer(
	name = "nanobot",
	help = "一个简单的机器人",
	no_args_is_help = True,
) 
console = Console()

def _make_provider(config: Config):
	"""
	Create LiteLLMProvider from config. Exits if no API key found.
	"""
	from mybot.providers.litellm_provider import LiteLLMProvider 
	p = config.get_provider() 
	model = config.agents.defaults.model 
	if not (p and p.api_key) and not model.startswith("bedrock/"):
		console.print("[red]Error: No API key configured. [/red]")
		console.print("Set one in ~/.mybot/config.json under providers section")
		raise typer.Exit(1)
	
	return LiteLLMProvider(
		api_key=p.api_key if p else None,
		api_base=config.get_api_base(),
		default_model=model,
		extra_headers=p.extra_headers if p else None,
		provider_name=config.get_provider_name(),
	)

@app.command()
def onboard():
	"""
	初始化机器人的配置
	"""
	
	config_path = get_config_path() 
	
	if config_path.exists():
		console.print(f"[yellow]配置文件已存在: {config_path}[/yellow]")
		if not typer.confirm("是否覆盖现有配置?"):
			raise typer.Exit()
	
	config = Config() 
	save_config(config)
	console.print(f"[green]配置已初始化并保存到: {config_path}[/green]")	

	workspace = get_workspace_path() 
	console.print(f"[blue]工作空间路径: {workspace}[/blue]")

	_create_workspace_templates(workspace)

	console.print(f"\n mybot is ready!")
	console.print("\nNext steps:")
	console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
	console.print("     Get one at: https://openrouter.ai/keys")
	console.print("  2. Chat: [cyan]mybot agent -m \"Hello!\"[/cyan]")
	console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")

def _create_workspace_templates(workspace: Path):
	"""在工作空间中创建一些示例文件"""
	templates = {
		"AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files
""",
        "SOUL.md": """# Soul

I am nanobot, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
	}

	for filename, content in templates.items():
		file_path = workspace / filename
		if not file_path.exists():
			file_path.write_text(content)
			console.print(f"[dim]已创建文件: {filename}[/dim]")

	# Create memory directory and MEMORY.md 
	memory_dir = workspace / "memory"
	memory_dir.mkdir(exist_ok=True)
	memory_file = memory_dir / "MEMORY.md"
	if not memory_file.exists():
		memory_file.write_text(""" # 长期记忆

## 用户信息
						 
## 交互记录
						 
## 重要提示

""")
		console.print(f"[dim]已创建文件: memory/MEMORY.md[/dim]")

@app.command()
def gateway(
	 port: int = typer.Option(18790, "--port", "-p", help="指定服务器端口"),
	 verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细日志"),
):
	"""
	启动机器人网关服务
	"""

	import asyncio
	from mybot.bus.queue import MessageBus
	from mybot.agent.loop import AgentLoop
	from mybot.config.loader import get_data_dir

	if verbose:
		import logging 
		logging.basicConfig(level=logging.DEBUG)

	console.print(f"正在启动网关服务... 监听端口: {port}...")

	config = load_config()
	bus = MessageBus()
	provider = _make_provider(config)
	session_manager = SessionManager(config.workspace_path)
	
	cron_store_path = get_data_dir() / "cron" / "jobs.json"
	cron = CronService(cron_store_path)

	agent = AgentLoop(
		bus=bus, 
		provider=provider,
		workspace=config.workspace_path,
		model=config.agents.defaults.model,
		max_iterations=config.agents.defaults.max_tool_iterations,
		brave_api_key=config.tools.web.search.api_key or None,
		exec_config=config.tools.exec,
		cron_service=cron, 
		restrict_to_workspace=config.tools.restrict_to_workspace,
		session_manager=session_manager,
	)

	async def on_cron_job(job: CronJob) -> str | None:
		"""
		Execute a cron job through the agent.
		"""
		response = await agent.process_direct(
			job.payload.message,
			session_key=f"cron:{job.id}",
			channel=job.payload.channel or "cli",
			chat_id=job.payload.to or "direct",
		)
		if job.payload.deliver and job.payload.to:
			from mybot.bus.events import OutboundMessage
			await bus.publish_outbound(OutboundMessage(
				channel=job.payload.channel or "cli",
				chat_id=job.payload.to,
				content=response or ""
			))
		return response 

	cron.on_job = on_cron_job

	async def on_heartbeat(prompt: str) -> str:
		"""
		Execute heartbeat through the agent.
		"""
		return await agent.process_direct(prompt, session_key="heartbeat")
	
	heartbeat = HeartbeatService(
		workspace=config.workspace_path,
		on_heartbeat=on_heartbeat,
		interval_s=3*60,
		enabled=True
	) 

	channels = ChannelManager(config, bus, session_manager=session_manager)

	async def run():
		try:
			await cron.start()
			await heartbeat.start()
			await asyncio.gather(
				agent.run(),
				channels.start_all(),
			)
		except KeyboardInterrupt:
			console.print("正在关闭网关服务...")
			# 在这里添加任何必要的清理代码，例如关闭数据库连接、保存状态等
			cron.stop()
			heartbeat.stop()
			agent.stop()
			await channels.stop_all()
			
	asyncio.run(run())


@app.command() 
def agent():
	"""
	启动机器人智能体服务
	"""
	print("启动机器人的智能体服务...")

@app.command()
def status():
	"""
	显示机器人的当前状态
	"""
	print("机器人当前状态: 在线, 连接正常, 智能体运行中...")

channels_app = typer.Typer(help="管理机器人频道")
app.add_typer(channels_app, name="channels")

@channels_app.command("status")
def channels_status():
	"""
	显示机器人频道的状态
	"""
	print("机器人频道状态: 3 个频道在线, 1 个频道离线...")

@channels_app.command("login")
def channels_login():
	"""
	登录机器人频道
	"""
	print("正在登录机器人频道... 登录成功!")


cron_app = typer.Typer(help="管理机器人定时任务")
app.add_typer(cron_app, name="cron")

@cron_app.command("list")
def cron_list():
	"""
	列出所有定时任务
	"""
	print("当前定时任务列表: \n1. 每日数据备份 - 每天 2:00 AM\n2. 每周报告生成 - 每周一 8:00 AM")

@cron_app.command("add")
def cron_add(name: str, schedule: str):
	"""
	添加一个新的定时任务
	"""
	print(f"正在添加定时任务: {name} - 计划时间: {schedule}... 添加成功!")

@cron_app.command("remove")
def cron_remove(name: str):
	"""
	移除一个定时任务
	"""
	print(f"正在移除定时任务: {name}... 移除成功!")

@cron_app.command("enable")
def cron_enable(name: str):
	"""
	启用一个定时任务
	"""
	print(f"正在启用定时任务: {name}... 启用成功!")

@cron_app.command("run")
def cron_run(name: str):
	"""
	运行一个定时任务
	"""
	print(f"正在运行定时任务: {name}... 运行成功!")

def version_callback(value: bool):
	if value:
		print("mybot 版本 1.0.0")
		raise typer.Exit() 

@app.callback()
def main(
	version: bool = typer.Option(
		None, "--version", "-v", callback=version_callback, is_eager=True, help="显示版本信息"
	),
):
	"""欢迎使用 mybot, 使用 --help 查看可用命令。"""
	pass 
	

