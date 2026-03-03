import asyncio 
from typing import Any
from datetime import date
from loguru import logger 
from email.message import EmailMessage
from mybot.agent.tools.base import Tool
from mybot.channels.email import EmailChannel
from mybot.bus.events import OutboundMessage
from mybot.config.schema import EmailConfig
from mybot.email.smtp import smtp_send



class EmailTool(Tool):
    """
    Tool to send and fetch emails.
    """
    def __init__(
        self, 
        config: EmailConfig):
        self.config = config 
    
    @property
    def name(self) -> str:
        return "email"

    @property
    def description(self) -> str:
        return "Send emails. Actions: send"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "fetch"],
                    "description": "Action to perform"
                },
                "to": {
                    "type": "string",
                    "description": "Recipient email address (for send)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject (for send)"
                },
                "body": {
                    "type": "string",
                    "description": "Email body/content (for send)"
                },
                # "start_date": {
                #     "type": "string",
                #     "description": "Start date in YYYY-MM-DD format (for fetch)"
                # },
                # "end_date": {
                #     "type": "string",
                #     "description": "End date in YYYY-MM-DD format (for fetch)"
                # },
                # "limit": {
                #     "type": "integer",
                #     "description": "Maximum number of emails to fetch (for fetch)"
                # }
            },
            "required": ["action"]
        }

    async def execute(
        self,
        action: str,
        to: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = 10,
        **kwargs: Any
    ) -> str:
        if action == "send":
            return await self._send_email(to, subject, body)
        elif action == "fetch":
            return self._fetch_emails(start_date, end_date, limit)
        return f"Unknown action: {action}"

    async def _send_email(self, to: str, subject: str, body: str) -> str:
        if not to:
            return "Error: recipient email address (to) is required for send"
        if not subject:
            return "Error: subject is required for send"
        if not body:
            return "Error: body is required for send"

        import smtplib
        import ssl 
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        try:
            # Use the email channel's send method directly
            email_msg = EmailMessage()
            email_msg["From"] = self.config.from_address or self.config.smtp_username or self.config.imap_username
            email_msg["To"] = to 
            email_msg["Subject"] = subject 
            email_msg.set_content(body)

            await asyncio.to_thread(smtp_send, self.config, email_msg)
            logger.info(f"发送邮件到 {to}")

        except Exception as e:
            return f"Error sending email: {str(e)}"
        
        return f"Successfully send email to {to}"

    def _fetch_emails(self, start_date_str: str, end_date_str: str, limit: int) -> str:
        logger.warning("fetch_emails() has not been implemented.")
        return ""