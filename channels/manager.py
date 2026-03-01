
import asyncio 
from loguru import logger
from mybot.config.schema import Config
from mybot.bus.queue import MessageBus
from mybot.session.manager import SessionManager
from mybot.channels.base import BaseChannel 
from mybot.channels.email import EmailChannel

class ChannelManager:
    def __init__(self, config: Config, bus: MessageBus, session_manager: "SessionManager | None" = None):
        self.config = config
        self.bus = bus
        self.session_manager = session_manager
        self.channels: dict[str, BaseChannel] = {}

        self._init_channels()
    
    def _init_channels(self) -> None:
        """
        _init_channels 的 Docstring
        
        :param self: 说明
        """
        if self.config.channels.email.enabled:
            try:
                from mybot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email,
                    self.bus,
                )
                logger.info("已启用 Email 渠道")

            except ImportError as e:
                logger.warning(f"无法导入 EmailChannel，跳过启动 Email 渠道: {e}")

    async def start_all(self):
        """
        start_all 的 Docstring
        
        :param self: 说明
        """
        if not self.channels:
            logger.warning("No channels enabled")
            return 
        
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        tasks = [] 
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self):
        """
        stop_all 的 Docstring
        
        :param self: 说明
        """
        logger.info("Stopping all channels...")

        # Stop dispatcher 
        if self._dispatch_task:
            self._dispatch_task.cancel() 
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass 

        # Stop all channels 
        for name, channel in self.channels.items():
            try:
                await channel.stop() 
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """
        _start_channel 的 Docstring
        
        :param self: 说明
        :param name: 说明
        :type name: str
        :param channel: 说明
        :type channel: BaseChannel
        """
        try:
            await channel.start()
        except Exception as e:
            logger.error(f"Failed to start channel {name}: {e}")

    async def _dispatch_outbound(self) -> None: 
        """
        _dispatch_outbound 的 Docstring
        
        :param self: 说明
        """
        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0 
                )

                logger.info(f"get outbound msg: {msg}")
                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error(f"Error sending to {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")

            except asyncio.TimeoutError:
                continue 
            except asyncio.CancelledError:
                break 