import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER = "ethan@sireapp.io"

TEMPLATE = """Hey {name},

I wanted to reach out to see what the process looks like for potentially being a guest on the show. I really love the work you guys put out and honestly feel like my generation needs more of it. We need more people standing up and talking about what they actually believe in.

I haven't done too many public appearances in the past since I live a pretty private life, but I'm looking to start doing more because I genuinely believe my story can inspire others and my message moves people. I've spoken at a few schools and to entrepreneur groups but I'd really like to make a larger impact on a broader scale.

For context, I'm 20 years old, based in New York City, and I founded a software company that now does a little over $5 million per year in revenue. I also lead a community of young entrepreneurs called the Taco Project, pretty interesting origin story, but all good people actually making a difference in the world.

Would love to learn more about the process and what the upcoming calendar looks like for you guys.

Thanks,
Ethan Williams
ethan@sireapp.io | +1 (734) 664-5129
Instagram: @ethan.williamsx"""

def send_email(contact: dict, opportunity: dict) -> bool:
    try:
        recipient = contact.get('email', '').strip()
        if not recipient or '@' not in recipient:
            return False
        name = contact.get('name')
        if name and name != 'null' and isinstance(name, str) and ' ' in name:
            name = name.strip().split()[0]
        elif not name or name == 'null':
            name = opportunity.get('name', 'there')
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = recipient
        msg['Subject'] = "Guest Appearance Inquiry"
        msg['Reply-To'] = GMAIL_USER
        msg.attach(MIMEText(TEMPLATE.format(name=name), 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, os.environ["GMAIL_APP_PASSWORD"])
            server.send_message(msg)
        return True
    except smtplib.SMTPRecipientsRefused:
        print(f"  ✗ Bad address: {contact.get('email')}")
        return False
    except Exception as e:
        print(f"  ✗ Send error: {e}")
        return False
