import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

logger = logging.getLogger(__name__)


async def send_verification_email(to_email: str, token: str) -> None:
    link = f"{settings.BASE_URL}/verify-email?token={token}"

    if not settings.SMTP_USER:
        logger.info(f"[DEV] Email verification link for {to_email}: {link}")
        print(f"\n[DEV] Verification link: {link}\n")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Подтвердите email — VSKS CRM"
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        html = f"""
        <html><body>
        <h2>Добро пожаловать в VSKS CRM!</h2>
        <p>Для завершения регистрации подтвердите ваш email:</p>
        <p><a href="{link}" style="background:#1976D2;color:white;padding:12px 24px;border-radius:4px;text-decoration:none;display:inline-block;">
            Подтвердить email
        </a></p>
        <p>Или перейдите по ссылке: <a href="{link}">{link}</a></p>
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
        <p><strong>Ваш логин для входа:</strong> {to_email}</p>
        <p style="color:#666;font-size:12px;">Если вы не регистрировались — проигнорируйте это письмо.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")


async def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{settings.BASE_URL}/reset-password?token={token}"

    if not settings.SMTP_USER:
        logger.info(f"[DEV] Password reset link for {to_email}: {link}")
        print(f"\n[DEV] Password reset link: {link}\n")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Сброс пароля — VSKS CRM"
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        html = f"""
        <html><body>
        <h2>Сброс пароля</h2>
        <p>Вы запросили сброс пароля для аккаунта <strong>{to_email}</strong>.</p>
        <p><a href="{link}" style="background:#1976D2;color:white;padding:12px 24px;border-radius:4px;text-decoration:none;display:inline-block;">
            Установить новый пароль
        </a></p>
        <p>Или перейдите по ссылке: <a href="{link}">{link}</a></p>
        <p style="color:#666;font-size:12px;">Ссылка действительна 1 час. Если вы не запрашивали сброс — проигнорируйте это письмо.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {e}")
