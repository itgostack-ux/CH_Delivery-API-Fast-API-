from app.api.v1.trip.services.email_service import EmailService

success = EmailService.send_mail(
    to="abiraj@gostack.in",
    subject="SMTP Test - GoFix",
    html="""
    <h2>SMTP Test Successful</h2>
    <p>This email was sent from the GoFix Delivery FastAPI application.</p>
    """
)

print(success)