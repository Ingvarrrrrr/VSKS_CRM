import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

logger = logging.getLogger(__name__)


def _effective_email_mode() -> str:
    """Единственное место, где решается, КАК слать почту (Правило №6 — один источник
    истины). settings.EMAIL_MODE — явный флаг ("console"/"login"/"relay"); если он не
    задан (пустая строка, значение по умолчанию) — старое поведение по SMTP_USER, чтобы
    ничего не сломать там, где EMAIL_MODE ещё не прописан в .env/docker-compose.yml.
    """
    mode = (settings.EMAIL_MODE or "").strip().lower()
    if mode in ("console", "login", "relay"):
        return mode
    return "login" if settings.SMTP_USER else "console"


def _smtp_send(msg: MIMEMultipart, to_email: str) -> None:
    """Единственное место, где письмо реально уходит по SMTP (Правило №6) — все три
    отправщика ниже вызывают только эту функцию, второй механизм отправки не заводим.
    """
    mode = _effective_email_mode()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        if mode == "login":
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        elif mode == "relay":
            # Свой контейнер mail/ внутри docker-сети (mail/main.cf: smtp_tls_security_level
            # = may) — STARTTLS только если сервер сам его предложит, без логина (relay
            # ограничивает отправителей своей docker-сетью, см. mail/main.cf mynetworks).
            try:
                if server.has_extn("starttls"):
                    server.starttls()
            except smtplib.SMTPException:
                logger.warning("STARTTLS to relay %s failed, sending without it", settings.SMTP_HOST)
        server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())


async def send_verification_email(to_email: str, token: str) -> None:
    link = f"{settings.BASE_URL}/verify-email?token={token}"

    if _effective_email_mode() == "console":
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

        _smtp_send(msg, to_email)
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")


async def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{settings.BASE_URL}/reset-password?token={token}"

    if _effective_email_mode() == "console":
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

        _smtp_send(msg, to_email)
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {e}")


async def send_account_locked_email(to_email: str) -> None:
    """Предупреждение о подборе пароля (app/auth/account_lockout.py) — шлётся
    ОДИН раз, когда счётчик неверных попыток для аккаунта доходит до лимита.
    Ошибка отправки не должна ронять логин — весь try/except ниже не
    пробрасывается наружу, по образцу остальных отправщиков в этом модуле."""
    if _effective_email_mode() == "console":
        logger.info(f"[DEV] Account lockout warning for {to_email}")
        print(f"\n[DEV] Account lockout warning email for {to_email}\n")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Подбор пароля к вашей учётной записи — GALA"
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        html = f"""
        <html><body>
        <h2>Подозрительная активность</h2>
        <p>Кто-то подбирает пароль к вашей учётной записи <strong>{to_email}</strong> в GALA.</p>
        <p>Вход в эту учётную запись временно заблокирован на 15 минут.</p>
        <p style="color:#c62828;"><strong>Если это были не вы — смените пароль после разблокировки.</strong></p>
        <p style="color:#666;font-size:12px;">Если это были вы и вы просто забыли пароль — воспользуйтесь формой «Забыли пароль?» после окончания блокировки.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        _smtp_send(msg, to_email)
    except Exception as e:
        logger.error(f"Failed to send account lockout email to {to_email}: {e}")
