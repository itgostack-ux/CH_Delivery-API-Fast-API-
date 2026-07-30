import os
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()


class EmailService:

    @staticmethod
    def send_mail(
        to: str,
        subject: str,
        html: str
    ) -> bool:

        from_email = os.getenv("FROM_EMAIL")
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = os.getenv("SMTP_PORT")
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")

        # Validate configuration
        if not from_email:
            raise RuntimeError("FROM_EMAIL not configured")

        if not smtp_server:
            raise RuntimeError("SMTP_SERVER not configured")

        if not smtp_port:
            raise RuntimeError("SMTP_PORT not configured")

        if not smtp_username:
            raise RuntimeError("SMTP_USERNAME not configured")

        if not smtp_password:
            raise RuntimeError("SMTP_PASSWORD not configured")

        msg = MIMEMultipart("alternative")

        msg["From"] = from_email
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(html, "html"))

        try:

            with smtplib.SMTP(
                smtp_server,
                int(smtp_port)
            ) as server:

                server.starttls()

                server.login(
                    smtp_username,
                    smtp_password
                )

                server.send_message(msg)

            return True

        except Exception as e:
            print(f"Email Error : {e}")
            return False

    @staticmethod
    def send_delivery_otp(
        recipient: str,
        manifest: str,
        driver: str,
        item_lines: int,
        total_qty: float,
        otp: str
    ) -> bool:

        subject = f"Delivery OTP - {manifest}"

        html = f"""
        <html>

        <body style="font-family:Arial;background:#f5f5f5;padding:25px;">

            <table width="650"
                   style="background:#ffffff;
                          border-radius:8px;
                          border:1px solid #dddddd;
                          padding:25px;">

                <tr>
                    <td style="
                        background:#111827;
                        color:white;
                        font-size:26px;
                        font-weight:bold;
                        padding:18px;">
                        GoFix - Transfer Delivery OTP
                    </td>
                </tr>

                <tr>
                    <td style="padding:25px;">

                        <p style="font-size:18px;">
                            A delivery is on its way to your store.
                        </p>

                        <table cellpadding="8">

                            <tr>
                                <td><b>Manifest</b></td>
                                <td>{manifest}</td>
                            </tr>

                            <tr>
                                <td><b>Driver</b></td>
                                <td>{driver}</td>
                            </tr>

                            <tr>
                                <td><b>Items</b></td>
                                <td>{item_lines} lines / {total_qty} units</td>
                            </tr>

                        </table>

                        <br>

                        <div style="
                            display:inline-block;
                            background:#0d6efd;
                            color:white;
                            padding:20px 35px;
                            font-size:34px;
                            font-weight:bold;
                            letter-spacing:6px;
                            border-radius:8px;">

                            OTP : {otp}

                        </div>

                        <br><br>

                        <div style="
                            background:#eef4ff;
                            padding:18px;
                            border-left:4px solid #0d6efd;">

                            Share this OTP with the driver only after
                            <b>physically verifying all items.</b>

                        </div>

                        <br>

                    </td>
                </tr>

                <tr>
                    <td style="
                        font-size:13px;
                        color:#999;
                        border-top:1px solid #eeeeee;
                        padding:18px;">

                        Sent via GoFix Logistics

                    </td>
                </tr>

            </table>

        </body>

        </html>
        """

        return EmailService.send_mail(
            recipient,
            subject,
            html
        )