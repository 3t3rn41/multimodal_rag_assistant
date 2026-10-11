"""Registration and password reset emails use authenticated TLS SMTP."""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from backend.core.config import settings
from backend.core.errors import ServiceError

logger = logging.getLogger(__name__)


def _deliver(message: EmailMessage):
    env = settings.env
    if not all((env.smtp_host, env.smtp_from, env.smtp_user, env.smtp_password)):
        raise ServiceError("发信服务尚未配置，请由网站管理员填写 SMTP 配置。", 503)
    context = ssl.create_default_context()
    if env.smtp_security == "ssl":
        smtp = smtplib.SMTP_SSL(
            env.smtp_host, env.smtp_port, timeout=10, context=context
        )
    else:
        smtp = smtplib.SMTP(env.smtp_host, env.smtp_port, timeout=10)
    with smtp:
        if env.smtp_security == "starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(env.smtp_user, env.smtp_password)
        smtp.send_message(message)


async def _send(message: EmailMessage):
    try:
        await asyncio.to_thread(_deliver, message)
    except ServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 - provider diagnostics can contain credentials
        logger.warning("email delivery failed error_type=%s", type(exc).__name__)
        raise ServiceError(
            "验证邮件发送失败，请稍后重发或联系网站管理员。", 503
        ) from None


async def send_registration_code(email: str, code: str, minutes: int):
    message = EmailMessage()
    message["From"] = settings.env.smtp_from
    message["To"] = email
    message["Subject"] = "注册验证码 · Multimodal RAG"
    message.set_content(
        f"你的注册验证码是：\n\n{code}\n\n"
        f"请在网站的验证码页面输入这 6 位数字。验证码在 {minutes} 分钟内有效，只能使用一次。\n"
        "重新获取验证码后，请使用最新邮件。请不要将验证码告诉他人。\n"
        "如果不是你发起的注册，请忽略这封邮件。"
    )
    await _send(message)


async def send_password_reset(email: str, token: str):
    link = f"{settings.env.public_base_url.rstrip('/')}/reset-password#token={token}"
    message = EmailMessage()
    message["From"] = settings.env.smtp_from
    message["To"] = email
    message["Subject"] = "重设登录密码 · Multimodal RAG"
    message.set_content(
        f"请打开以下链接设置新密码：\n\n{link}\n\n"
        f"链接在 {settings.env.auth_token_minutes} 分钟内有效，只能使用一次。\n"
        "如果不是你发起的操作，请忽略这封邮件。"
    )
    await _send(message)
