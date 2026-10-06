import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


class EmailService:

    @staticmethod
    def send_mail(to: str, subject: str, html: str) -> bool:

        if not (settings.SMTP_SERVER and settings.SMTP_USERNAME
                and settings.SMTP_PASSWORD and settings.FROM_EMAIL):
            raise RuntimeError("SMTP is not configured (check app/.env)")

        msg = MIMEMultipart("alternative")
        msg["From"] = settings.FROM_EMAIL
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)

        return True

    @staticmethod
    def send_login_otp(to: str, full_name: str, otp: str, expires_minutes: int) -> bool:

        html = f"""
        <html><body style="font-family:Arial;background:#f5f5f5;padding:25px;">
          <table width="520" style="background:#fff;margin:auto;padding:30px;border-radius:8px;">
            <tr><td>
              <h2 style="margin-top:0;">CH Delivery - Login OTP</h2>
              <p>Hi {full_name},</p>
              <p>Use the code below to sign in. It expires in {expires_minutes} minutes.</p>
              <p style="font-size:32px;letter-spacing:8px;font-weight:bold;margin:25px 0;">{otp}</p>
              <p style="color:#777;font-size:12px;">If you did not request this, you can ignore this email.</p>
            </td></tr>
          </table>
        </body></html>
        """

        return EmailService.send_mail(to, "Your CH Delivery login OTP", html)
