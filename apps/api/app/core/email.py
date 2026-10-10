"""
Email service for sending notifications
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """
    Send an email notification.
    In development, uses MailHog (SMTP on localhost:1025).
    In production, uses configured SMTP settings.
    
    Returns True if sent successfully, False otherwise.
    """
    try:
        # Determine SMTP settings based on environment
        if settings.ENVIRONMENT == "development":
            smtp_host = settings.SMTP_HOST_DEV
            smtp_port = settings.SMTP_PORT_DEV
            smtp_user = None
            smtp_password = None
            use_tls = False
        else:
            smtp_host = settings.SMTP_HOST
            smtp_port = settings.SMTP_PORT
            smtp_user = settings.SMTP_USER
            smtp_password = settings.SMTP_PASSWORD
            use_tls = True
        
        if not smtp_host:
            logger.warning("SMTP_HOST not configured, skipping email send")
            return False
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        
        # Add text and HTML parts
        if text_body:
            text_part = MIMEText(text_body, "plain")
            msg.attach(text_part)
        
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_email}: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def format_opportunity_email(opportunity: dict, domain_name: str) -> tuple[str, str]:
    """
    Format an opportunity notification email.
    Returns (subject, html_body).
    """
    signal_type_labels = {
        "jobs": "Recrutement",
        "pricing_change": "Changement de tarification",
        "tool_added": "Nouvel outil détecté",
        "new_product": "Nouveau produit",
        "partnership": "Partenariat",
        "expansion": "Expansion",
        "funding": "Financement",
        "new_site": "Nouveau site",
        "page_redesign": "Refonte de la page",
        "recent_activity": "Activité récente",
        "minor_activity": "Modification mineure",
    }
    
    signal_label = signal_type_labels.get(opportunity.get("signal_type", ""), "Signal détecté")
    company_name = opportunity.get("company_name", domain_name)
    score = opportunity.get("score", 0)
    proof_url = opportunity.get("proof_url", "")
    why_it_matters = opportunity.get("why_it_matters", "")
    suggested_approach = opportunity.get("suggested_approach", "")
    
    subject = f"🎯 Nouvelle opportunité : {company_name} - {signal_label}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4F46E5; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 20px; border-radius: 0 0 8px 8px; }}
            .score {{ display: inline-block; background-color: #10B981; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
            .button {{ display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
            .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Nouvelle Opportunité Détectée</h1>
            </div>
            <div class="content">
                <h2>{company_name}</h2>
                <p><strong>Type de signal :</strong> {signal_label}</p>
                <p><span class="score">Score : {score}/100</span></p>
                
                <h3>Pourquoi c'est important :</h3>
                <p>{why_it_matters or "Cette opportunité pourrait être pertinente pour votre organisation."}</p>
                
                {f'<h3>Approche suggérée :</h3><p>{suggested_approach}</p>' if suggested_approach else ''}
                
                <p><a href="{proof_url}" class="button">Voir la preuve</a></p>
                
                <div class="footer">
                    <p>Vous recevez cet email car vous êtes abonné aux notifications Early Signals.</p>
                    <p>Pour modifier vos préférences, connectez-vous à votre compte.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
Nouvelle Opportunité Détectée

{company_name}
Type de signal : {signal_label}
Score : {score}/100

Pourquoi c'est important :
{why_it_matters or "Cette opportunité pourrait être pertinente pour votre organisation."}

{f'Approche suggérée :\n{suggested_approach}\n' if suggested_approach else ''}

Voir la preuve : {proof_url}

---
Vous recevez cet email car vous êtes abonné aux notifications Early Signals.
Pour modifier vos préférences, connectez-vous à votre compte.
    """
    
    return subject, html_body
