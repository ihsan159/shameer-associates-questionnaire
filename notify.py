"""
notify.py
Modular notification system for Shameer Associates.
Supports email (SMTP stub / real) and is structured for WhatsApp addition later.
"""
import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# Configuration (read from environment variables)
# Set these in your .env or environment:
#   SA_SMTP_HOST, SA_SMTP_PORT, SA_SMTP_USER, SA_SMTP_PASS
#   SA_NOTIFY_FROM, SA_NOTIFY_TO (comma-separated)
#   SA_APP_BASE_URL (e.g. http://localhost:5000)
# ----------------------------------------------------------

SMTP_HOST = os.environ.get('SA_SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SA_SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SA_SMTP_USER', '')
SMTP_PASS = os.environ.get('SA_SMTP_PASS', '')
NOTIFY_FROM = os.environ.get('SA_NOTIFY_FROM', 'noreply@shameerassociates.com')
NOTIFY_TO_RAW = os.environ.get('SA_NOTIFY_TO', '')
NOTIFY_TO = [e.strip() for e in NOTIFY_TO_RAW.split(',') if e.strip()]
APP_BASE_URL = os.environ.get('SA_APP_BASE_URL', 'http://localhost:5000')

SMTP_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASS and NOTIFY_TO)


def _send_email(subject, html_body, to_addresses=None):
    recipients = to_addresses or NOTIFY_TO
    if not recipients:
        logger.info("[NOTIFY] No email recipients configured — skipping email send.")
        return False
    if not SMTP_ENABLED:
        logger.info("[NOTIFY] SMTP not configured. Would have sent:\nTo: %s\nSubject: %s\n%s",
                    recipients, subject, html_body)
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = NOTIFY_FROM
        msg['To'] = ', '.join(recipients)
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(NOTIFY_FROM, recipients, msg.as_string())
        logger.info("[NOTIFY] Email sent to %s: %s", recipients, subject)
        return True
    except Exception as e:
        logger.error("[NOTIFY] Email send failed: %s", e)
        return False


def notify_new_submission(project):
    """Send notification when a client submits their questionnaire."""
    project_uid = project.get('project_uid', '—')
    client_name = project.get('client_name', 'Client')
    location = project.get('location', '—')
    project_type = project.get('project_type', '—')
    completion = project.get('progress_percent', 0)
    project_id = project.get('id', '')

    project_url = f"{APP_BASE_URL}/architect/?project={project_id}"

    subject = f"[Shameer Associates] New Design Questionnaire — {client_name}"
    html_body = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #FBFBF9; border: 1px solid #E5E3DC;">
      <div style="background: #121212; color: #fff; padding: 24px 32px;">
        <h1 style="margin: 0; font-size: 18px; letter-spacing: 0.2em; font-weight: 700;">SHAMEER ASSOCIATES</h1>
        <p style="margin: 4px 0 0; font-size: 11px; letter-spacing: 0.25em; color: #A0825B; text-transform: uppercase;">Architecture · Interiors · Landscape</p>
      </div>
      <div style="padding: 32px;">
        <h2 style="font-size: 20px; color: #121212; margin-top: 0;">New Design Questionnaire Received</h2>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr><td style="padding: 8px 0; color: #737373; width: 160px;">Client</td><td style="padding: 8px 0; font-weight: 600; color: #121212;">{client_name}</td></tr>
          <tr><td style="padding: 8px 0; color: #737373;">Project ID</td><td style="padding: 8px 0; font-weight: 600; color: #121212;">{project_uid}</td></tr>
          <tr><td style="padding: 8px 0; color: #737373;">Location</td><td style="padding: 8px 0; color: #4A4A4A;">{location}</td></tr>
          <tr><td style="padding: 8px 0; color: #737373;">Project Type</td><td style="padding: 8px 0; color: #4A4A4A;">{project_type}</td></tr>
          <tr><td style="padding: 8px 0; color: #737373;">Completion</td><td style="padding: 8px 0; color: #4A4A4A;">{completion}%</td></tr>
        </table>
        <div style="margin-top: 28px;">
          <a href="{project_url}" style="display: inline-block; background: #121212; color: #fff; text-decoration: none; padding: 12px 28px; font-size: 12px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase;">
            OPEN PROJECT
          </a>
        </div>
        <p style="font-size: 12px; color: #737373; margin-top: 24px; border-top: 1px solid #E5E3DC; padding-top: 16px;">
          This is an automated notification from the Shameer Associates Digital Workspace. Do not reply to this email.
        </p>
      </div>
    </div>
    """
    _send_email(subject, html_body)


# Pluggable provider interface (WhatsApp ready):
def notify_whatsapp(project):
    """
    Placeholder for WhatsApp notification.
    Wire in a provider (e.g. Twilio, WATI, Meta Cloud API) without rebuilding anything.
    """
    # Example: call WhatsApp provider API with project data
    # provider = WhatsAppProvider(api_key=os.environ.get('SA_WA_KEY'))
    # provider.send_template(to=NOTIFY_WA_NUMBER, template='new_submission', params={...})
    logger.info("[NOTIFY] WhatsApp notification placeholder called for project %s", project.get('project_uid'))
