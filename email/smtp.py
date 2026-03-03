import smtplib 
import ssl 
from email.message import EmailMessage 
from mybot.config.schema import EmailConfig 

def smtp_send(config: EmailConfig, msg: EmailMessage) -> None:
    timeout = 30
    if config.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            config.smtp_host,
            config.smtp_port,
            timeout=timeout,
        ) as smtp:
            smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(msg)
            return 

    with smtplib.SMTP(
        config.smtp_host,
        config.smtp_port,
        timeout=timeout, 
    ) as smtp:
        if config.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(msg)
