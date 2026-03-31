import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(contact: dict, opportunity: dict, config: dict = None) -> bool:
    cfg = config or {}
    gmail_user = cfg.get("senderEmail") or os.environ.get("GMAIL_USER", "ethan@sireapp.io")
    sender_name = cfg.get("senderName", "Ethan Williams")
    subject = cfg.get("emailSubject", "Guest Appearance - Ethan Williams")
    template = cfg.get("template", "")

    if not template:
        template = """Hey, I wanted to reach out to see what the process looks like for potentially being a guest on the platform. I really love the work you guys put out and honestly feel like my generation needs more of it.

For context, I'm 20 years old, based in New York City, and I founded a software company that now does a little over $5 million per year in revenue. I also lead a community of young entrepreneurs called the Taco Project.

Would love to learn more about the process and what the upcoming calendar looks like for you guys.

Thanks,
Ethan Williams
ethan@sireapp.io | +1 (734) 664-5129
Instagram: @ethan.williamsx"""

    try:
        recipient = (contact.get('email') or '').strip()
        if not recipient or '@' not in recipient:
            return False

        msg = MIMEMultipart()
        msg['From'] = f"{sender_name} <{gmail_user}>"
        msg['To'] = recipient
        msg['Subject'] = subject
        msg['Reply-To'] = gmail_user
        msg.attach(MIMEText(template, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, os.environ["GMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True
    except smtplib.SMTPRecipientsRefused:
        print(f"  ✗ Bad address: {contact.get('email')}")
        return False
    except Exception as e:
        print(f"  ✗ Send error: {e}")
        return False
