import asyncio
import json  
from pathlib import Path
from loguru import logger
from mybot.providers.base import LLMProvider
from mybot.bus.queue import MessageBus
from mybot.bus.events import InboundMessage, OutboundMessage
from mybot.session.manager import SessionManager
from mybot.config.schema import ExecToolConfig, EmailConfig
from mybot.cron.service import CronService
from mybot.agent.context import ContextBuilder
from mybot.agent.subagent import SubagentManager
from mybot.agent.tools.registry import ToolRegistry
from mybot.agent.tools.message import MessageTool
from mybot.agent.tools.spawn import SpawnTool
from mybot.agent.tools.shell import ExecTool
from mybot.agent.tools.web import WebFetchTool, WebSearchTool
from mybot.agent.tools.cron import CronTool
from mybot.agent.tools.email import EmailTool
from mybot.agent.tools.filsystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool


class AgentLoop:
    def __init__(
        self, 
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        search_api_key: str | None = None,
        search_engine: str | None = None,
        exec_config: "ExecToolConfig | None" = None, 
        cron_service: "CronService | None" = None,
        email_config: "EmailConfig | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None, 
    ):
        self.bus = bus
        self.provider = provider 
        self.workspace = workspace
        self.model = model or provider.get_default_model() 
        self.max_iterations = max_iterations
        self.search_api_key = search_api_key
        self.search_engine = search_engine
        self.exec_config = exec_config or ExecToolConfig()
        self.email_config = email_config
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace 

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace, 
            bus=bus,
            model=self.model,
            search_api_key=search_api_key,
            search_engine=search_engine,
            exec_config=self.exec_config,
            email_config=self.email_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False 
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """
        Regiser the default set of tools.
        """
        allowed_dir = self.workspace if self.restrict_to_workspace else None 
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))

        self.tools.register(WebSearchTool(
            api_key=self.search_api_key,
            engine=self.search_engine
            ))
        self.tools.register(WebFetchTool())

        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)

        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)

        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        self.tools.register(EmailTool(self.email_config))

    async def run(self) -> None:
        self._running = True
        logger.info("Agent loop started.")
        
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(), 
                    timeout=1.0
                )

                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        logger.info(f"publish outbound response: {response}")
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response 
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))

            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        """
        stop 的 Docstring
        
        :param self: 说明
        """
        self._running = False 
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        _process_message 的 Docstring
        
        :param self: 说明
        :param msg: 说明
        :type msg: InboundMessage
        :return: 说明
        :rtype: OutboundMessage | None
        """
        if msg.channel == "system":
            return await self._process_system_message(msg) 
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content 
        logger.info(f"处理来自 {msg.channel}:{msg.sender_id} 的消息: {preview}")

        session = self.sessions.get_or_create(msg.session_key)

        message_tool = self.tools.get("message") 
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)

        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id) 
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)

        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content, 
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        iteration = 0 
        final_content = None 

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(), 
                model=self.model, 
            )

            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name, 
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, 
                    response.content, 
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name} ({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result 
                    )
            else:
                final_content = response.content 
                break 
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content 
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")

        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        """
        logger.info(f"Processing system message from {msg.sender_id}")

        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            origin_channel = "cli"
            origin_chat_id = msg.chat_id 

        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)

        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)

        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)

        email_tool = self.tools.get("email")
        if isinstance(email_tool, EmailTool):
            email_tool.set_context(origin_channel, origin_chat_id)

        messages = self.context.build_messages(
            history=session.get_history(),
            current_mesage=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )

        iteration = 0
        final_content = None 
        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
               messages=messages,
               tools=self.tools.get_definitions(),
               model=self.model,  
            )

            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name, 
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]

                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result 
                    )

            else:
                final_content = response.content
                break 

        if final_content is None:
            final_content = "Background task completed."

        session.add_message("user", f"[System: {msg.sender_id} {msg.content}]")
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage (
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content,
        )

    async def process_direct(
        self,
        content: str, 
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str: 
        """
        Process a message directly (for CLI or cron usage).
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content, 
        )

        response = await self._process_message(msg)
        return response.content if response else ""