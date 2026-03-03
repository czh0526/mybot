import asyncio
import imaplib
import smtplib
import ssl
import re 
import html
from datetime import date
from typing import Any
from loguru import logger
from email import policy 
from email.header import decode_header, make_header 
from email.message import EmailMessage 
from email.parser import BytesParser 
from email.utils import parseaddr 
from mybot.channels.base import BaseChannel
from mybot.config.schema import EmailConfig
from mybot.bus.queue import MessageBus
from mybot.bus.events import OutboundMessage 
from mybot.email.smtp import smtp_send 

class EmailChannel(BaseChannel):
    """
    Email Channel.

    Inbound:
    - 监听指定邮箱的邮件，提取邮件内容和附件，发送到消息总线

    Outbound:
    - 监听消息总线上的 outbound_email 消息，发送邮件到指定地址  
    """

    name = "email"
    _IMP_MONTHS = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    )

    def __init__(self, config: EmailConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: EmailConfig = config
        self._last_subject_by_chat: dict[str, str] = {}
        self._last_message_id_by_chat: dict[str, str] = {}
        self._processed_uids: set[str] = set()
        self._MAX_PROCESSED_UIDS = 100000

    async def start(self) -> None:
        """
        启动邮箱监听服务，定期检查新邮件并处理
        """
        if not self.config.consent_granted:
            logger.warning("Email channel is not enabled because consent is not granted.")
            return
        
        if not self._validate_config():
            return
        
        self._running = True 
        logger.info("Starting Email channel (IMAP polling mode)...")

        poll_seconds = max(5, int(self.config.poll_interval_seconds))
        while self._running:
            try:
                inbound_items = await asyncio.to_thread(self._fetch_new_messages)
                for item in inbound_items:
                    sender = item["sender"]
                    subject = item.get("subject", "")
                    message_id = item.get("message_id", "")

                    if subject:
                        self._last_subject_by_chat[sender] = subject 
                    if message_id:
                        self._last_message_id_by_chat[sender] = message_id
                    
                    await self._handle_message(
                        sender_id=sender,
                        chat_id=sender,
                        content=item["content"],
                        metadata=item.get("metadata", {}),
                    )

            except Exception as e:
                logger.error(f"Error in Email channel loop: {e}")

            await asyncio.sleep(poll_seconds)

    async def stop(self) -> None:
        """
        停止邮箱监听服务
        """
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send email via SMTP.
        """
        if not self.config.consent_granted:
            logger.warning("Skip email send: consent_granted is false")
            return 
        
        force_send = bool((msg.metadata or {}).get("force_send"))
        if not self.config.auto_reply_enabled and not force_send:
            logger.info("Skip automatic email reply: auto_reply_enabled is false")
            return 

        if not self.config.smtp_host:
            logger.warning("Email channel SMTP host not configured")
            return 
        
        to_addr = msg.chat_id.strip()
        if not to_addr:
            logger.warning("Email channel missing recipient address")
            return 
        
        base_subject = self._last_subject_by_chat.get(to_addr, "mybot reply")
        subject = self._reply_subject(base_subject)
        if msg.metadata and isinstance(msg.metadata.get("subject"), str):
            override = msg.metadata["subject"].strip()
            if override:
                subject = override

        email_msg = EmailMessage()
        email_msg["From"] = self.config.from_address or self.config.smtp_username or self.config.imap_username
        email_msg["To"] = to_addr 
        email_msg["Subject"] = subject 
        email_msg.set_content(msg.content or "")

        in_reply_to = self._last_message_id_by_chat.get(to_addr)
        if in_reply_to:
            email_msg["In-Reply-To"] = in_reply_to 
            email_msg["References"] = in_reply_to

        try:
            await asyncio.to_thread(smtp_send, self.config, email_msg)
        except Exception as e:
            logger.error(f"Error sending email to {to_addr}: {e}")
            raise 

    
    def _reply_subject(self, base_subject: str) -> str:
        subject = (base_subject or "").strip() or "mybot reply"
        prefix = self.config.subject_prefix or "Re: "
        if subject.lower().startswith("re:"):
            return subject
        return f"{prefix}{subject}"

    def _validate_config(self) -> bool:
        missing = [] 
        if not self.config.imap_host:
            missing.append("imap_host")
        if not self.config.imap_username:
            missing.append("imap_username")
        if not self.config.imap_password:
            missing.append("imap_password")
        if not self.config.smtp_host:
            missing.append("smtp_host")
        if not self.config.smtp_username:
            missing.append("smtp_username")
        if not self.config.smtp_password:
            missing.append("smtp_password")
        
        if missing:
            logger.error(f"Email channel not configured, missing: {', '.join(missing)}")
            return False 
        return True 

    def _fetch_new_messages(self) -> list[dict[str, Any]]:
        """
        连接邮箱服务器，检查新邮件，提取内容和附件，返回消息列表
        """
        return self._fetch_messages(
            search_criteria=("UNSEEN",),
            mark_seen=self.config.mark_seen,
            dedupe=True,
            limit=1,
        )
    
    def fetch_messages_between_dates(
            self,
            start_date: date, 
            end_date: date,
            limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        获取指定日期范围内的邮件，提取内容和附件，返回消息列表
        """
        if end_date <= start_date:
            return []
        
        return self._fetch_messages(
            search_criteria=(
                "SINCE",
                self._format_imap_date(start_date),
                "BEFORE",
                self._format_imap_date(end_date),
            ),
            mark_seen=False,
            dedupe=False,
            limit=max(1, int(limit)),
        )
    
    def _fetch_messages(
        self,
        search_criteria: tuple[str, ...],
        mark_seen: bool,
        dedupe: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        """
        连接邮箱服务器，按照搜索条件检查邮件，提取内容和附件，返回消息列表
        """
        messages: list[dict[str, Any]] = []
        mailbox = self.config.imap_mailbox or "INBOX"

        if self.config.imap_use_ssl:
            client = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
        else:
            client = imaplib.IMAP4(self.config.imap_host, self.config.imap_port)

        try:
            client.login(self.config.imap_username, self.config.imap_password)
            status, _ = client.select(mailbox)
            if status != "OK":
                return messages 
            
            status, data = client.search(None, *search_criteria)
            if status != "OK" or not data:
                return messages
            
            ids = data[0].split()
            if limit > 0 and len(ids) > limit:
                ids = ids[-limit:]
            for imap_id in ids:
                status, fetched = client.fetch(imap_id, "(BODY.PEEK[] UID)")
                if status != "OK" or not fetched:
                    continue

                raw_bytes = self._extract_message_bytes(fetched)
                if raw_bytes is None:
                    continue

                uid = self._extract_uid(fetched)
                if dedupe and uid and uid in self._processed_uids:
                    continue 

                parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                sender = parseaddr(parsed.get("From", ""))[1].strip().lower() 
                if not sender: 
                    continue 

                subject = self._decode_header_value(parsed.get("Subject", ""))
                date_value = parsed.get("Date", "")
                message_id = parsed.get("Mesage-ID", "").strip() 
                body = self._extract_text_body(parsed)

                if not body:
                    body = "(empty email body)"
                
                body = body[: self.config.max_body_chars]
                content = (
                    f"Email received.\n"
                    f"From: {sender}\n"
                    f"Subject: {subject}\n"
                    f"Date: {date_value}\n\n"
                    f"{body}"
                )

                metadata = {
                    "message_id": message_id,
                    "subject": subject,
                    "date": date_value,
                    "sender_email": sender,
                    "uid": uid,
                }
                messages.append(
                    {
                        "sender": sender,
                        "subject": subject,
                        "message_id": message_id,
                        "content": content,
                        "metadta": metadata,
                    }
                )

                if dedupe and uid:
                    self._processed_uids.add(uid)
                    if len(self._processed_uids) > self._MAX_PROCESSED_UIDS:
                        self._processed_uids.clear()

                if mark_seen:
                    client.store(imap_id, "+FLAGS", "\\Seen")

        finally:
            try:
                client.logout()
            except Exception:
                pass
        
        return messages 

    
    @staticmethod 
    def _extract_message_bytes(fetched: list[Any]) -> bytes | None:
        for item in fetched:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        return None 

    @staticmethod 
    def _extract_uid(fetched: list[Any]) -> str:
        for item in fetched:
            if isinstance(item, tuple) and item and isinstance(item[0], (bytes, bytearray)):
                head = bytes(item[0]).decode("utf-8", errors="ignore")
                m = re.search(r"UID\s+(\d+)", head)
                if m:
                    return m.group(1)
        
        return ""

    @staticmethod 
    def _decode_header_value(value: str) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value 

    @classmethod 
    def _extract_text_body(cls, msg: Any) -> str:
        """
        _extract_text_body 的 Docstring
        
        :param cls: 说明
        :param msg: 说明
        :type msg: Any
        :return: 说明
        :rtype: str
        """
        if msg.is_multipart():
            plain_parts: list[str] = [] 
            html_parts: list[str] = [] 
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    continue 
                content_type = part.get_content_type() 
                try:
                    payload = part.get_content()
                except Exception:
                    payload_bytes = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload_bytes.decode(charset, errors="replace")
                if not isinstance(payload, str):
                    continue
                if content_type == "text/plain":
                    plain_parts.append(payload)
                elif content_type == "text/html":
                    html_parts.append(payload)
            if plain_parts:
                return "\n\n".join(plain_parts).strip()
            if html_parts:
                return cls._html_to_text("\n\n".join(html_parts)).strip()
            return ""
        
        try:
            payload = msg.get_content()
        except Exception:
            payload_bytes = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            payload = payload_bytes.decode(charset, errors="replace")
        if not isinstance(payload, str):
            return ""
        if msg.get_content_type() == "text/html":
            return cls._html_to_text(payload).strip()
        return payload.strip()
    
    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        text = re.sub(r"<\s*br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"<\s*/\s*p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)
