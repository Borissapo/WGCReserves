"""
Professional HTML email alerts with embedded Matplotlib charts.

Supports two delivery methods (chosen automatically):
  1. Outlook COM (win32com) — used on Windows when Outlook is available.
  2. SMTP — used on Linux / CI when SMTP_* env vars are configured.
     Works with Office 365: smtp.office365.com:587.

Env vars (in .env or GitHub Secrets):
  RECEIVER_EMAIL  — recipient address
  SMTP_SERVER     — e.g. smtp.office365.com  (enables SMTP mode)
  SMTP_PORT       — e.g. 587
  SMTP_USER       — sender email (usually same as the account)
  SMTP_PASSWORD   — password or app password
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

STREAMLIT_URL = "https://goldreservesvista.streamlit.app/HF_Central_Bank_Monitor"


def send_alert(
    country: str,
    old_tonnes: float | None,
    new_tonnes: float,
    report_date: str,
    source_url: str,
    rolling_chart_path: str | None = None,
    flow_chart_path: str | None = None,
) -> None:
    """Send an HTML email with an executive summary and embedded charts."""

    change = new_tonnes - old_tonnes if old_tonnes is not None else 0.0
    change_str = f"{change:+,.2f}" if old_tonnes is not None else "N/A (first)"
    change_color = "#00c853" if change >= 0 else "#ff1744"

    subject = f"\U0001f6a8 GOLD ALERT: {country} Updated Reserves"

    html = _build_html(
        country=country,
        old_tonnes=old_tonnes,
        new_tonnes=new_tonnes,
        change=change,
        change_str=change_str,
        change_color=change_color,
        report_date=report_date,
        source_url=source_url,
        has_rolling=rolling_chart_path is not None,
        has_flow=flow_chart_path is not None,
    )

    if not RECEIVER_EMAIL:
        print("  [EMAIL SKIPPED] RECEIVER_EMAIL not set in .env")
        print(f"  Subject: {subject}")
        print(f"  {country}: {old_tonnes} -> {new_tonnes} ({change_str})")
        return

    inline_images = {}
    if rolling_chart_path:
        inline_images["rolling_chart"] = rolling_chart_path
    if flow_chart_path:
        inline_images["flow_chart"] = flow_chart_path

    # Choose delivery method
    if SMTP_SERVER and SMTP_USER and SMTP_PASSWORD:
        _send_via_smtp(
            to=RECEIVER_EMAIL,
            subject=subject,
            html_body=html,
            inline_images=inline_images,
        )
    else:
        _send_via_outlook(
            to=RECEIVER_EMAIL,
            subject=subject,
            html_body=html,
            inline_images=inline_images,
        )
    print(f"  [EMAIL SENT] Alert delivered to {RECEIVER_EMAIL}")


# ------------------------------------------------------------------
# SMTP delivery (Office 365 / any SMTP server)
# ------------------------------------------------------------------

def _send_via_smtp(
    to: str,
    subject: str,
    html_body: str,
    inline_images: dict[str, str] | None = None,
) -> None:
    """Send email via SMTP with TLS (works with Office 365, Gmail, etc.)."""
    msg = MIMEMultipart("related")
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    if inline_images:
        for cid, path in inline_images.items():
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                img = MIMEImage(f.read())
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
            msg.attach(img)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to, msg.as_string())


# ------------------------------------------------------------------
# Outlook COM delivery (Windows local)
# ------------------------------------------------------------------

PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_ATTACH_FLAGS = "http://schemas.microsoft.com/mapi/proptag/0x37140003"


def _send_via_outlook(
    to: str,
    subject: str,
    html_body: str,
    inline_images: dict[str, str] | None = None,
) -> None:
    """Create and send an Outlook MailItem with inline-embedded images."""
    try:
        import win32com.client
    except ImportError:
        print("  [EMAIL SKIPPED] win32com not available (non-Windows environment)")
        return

    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # olMailItem = 0
    mail.To = to
    mail.Subject = subject
    mail.HTMLBody = html_body

    if inline_images:
        for cid, path in inline_images.items():
            if not os.path.isfile(path):
                continue
            att = mail.Attachments.Add(os.path.abspath(path))
            att.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, cid)
            att.PropertyAccessor.SetProperty(PR_ATTACH_FLAGS, 4)  # ATT_MHTML_REF

    mail.Send()


# ------------------------------------------------------------------
# HTML builder
# ------------------------------------------------------------------

def _build_html(
    country: str,
    old_tonnes: float | None,
    new_tonnes: float,
    change: float,
    change_str: str,
    change_color: str,
    report_date: str,
    source_url: str,
    has_rolling: bool,
    has_flow: bool,
) -> str:
    old_display = f"{old_tonnes:,.2f}" if old_tonnes is not None else "N/A"

    charts_html = ""
    if has_rolling:
        charts_html += (
            '<h3 style="color:#FFD700; margin-top:28px;">Rolling Gold Reserves</h3>'
            '<img src="cid:rolling_chart" '
            'style="width:100%; max-width:680px; border-radius:6px;" />'
        )
    if has_flow:
        charts_html += (
            '<h3 style="color:#FFD700; margin-top:28px;">Monthly Net Flow</h3>'
            '<img src="cid:flow_chart" '
            'style="width:100%; max-width:680px; border-radius:6px;" />'
        )

    return f"""\
<html>
<body style="margin:0; padding:0; background:#0f0f23; font-family:Segoe UI,Arial,sans-serif;">
<div style="max-width:720px; margin:0 auto; padding:24px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border-radius:8px;
              padding:20px 24px; text-align:center; border-bottom:3px solid #FFD700;">
    <h1 style="margin:0; color:#FFD700; font-size:22px;">
      \U0001f6a8 Gold Reserve Alert
    </h1>
    <p style="margin:6px 0 0; color:#a0a0c0; font-size:13px;">
      Central Banks Gold Monitor
    </p>
  </div>

  <!-- Executive Summary Table -->
  <table style="width:100%; border-collapse:collapse; margin-top:20px;
                background:#16213e; border-radius:8px; overflow:hidden;">
    <thead>
      <tr style="background:#1a1a2e;">
        <th style="padding:10px 14px; color:#FFD700; text-align:left; font-size:13px;
                   border-bottom:1px solid #2a2a4a;">Field</th>
        <th style="padding:10px 14px; color:#FFD700; text-align:left; font-size:13px;
                   border-bottom:1px solid #2a2a4a;">Value</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Country</td>
        <td style="padding:9px 14px; color:#fff; font-weight:600;
                   border-bottom:1px solid #2a2a4a;">{country}</td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Prior Tonnes</td>
        <td style="padding:9px 14px; color:#fff; border-bottom:1px solid #2a2a4a;">{old_display}</td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Current Tonnes</td>
        <td style="padding:9px 14px; color:#fff; font-weight:600;
                   border-bottom:1px solid #2a2a4a;">{new_tonnes:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Change</td>
        <td style="padding:9px 14px; color:{change_color}; font-weight:700; font-size:15px;
                   border-bottom:1px solid #2a2a4a;">{change_str} tonnes</td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Report Date</td>
        <td style="padding:9px 14px; color:#fff; border-bottom:1px solid #2a2a4a;">{report_date}</td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0; border-bottom:1px solid #2a2a4a;">Source</td>
        <td style="padding:9px 14px; border-bottom:1px solid #2a2a4a;">
          <a href="{source_url}" style="color:#64b5f6; text-decoration:none;">View Source Data</a>
        </td>
      </tr>
      <tr>
        <td style="padding:9px 14px; color:#c0c0c0;">Dashboard</td>
        <td style="padding:9px 14px;">
          <a href="{STREAMLIT_URL}" style="color:#64b5f6; text-decoration:none;">
            Open HF Central Bank Monitor
          </a>
        </td>
      </tr>
    </tbody>
  </table>

  <!-- Charts -->
  {charts_html}

  <!-- Footer -->
  <p style="margin-top:30px; color:#555; font-size:11px; text-align:center;
            border-top:1px solid #2a2a4a; padding-top:14px;">
    Central Banks Gold Monitor &mdash; Automated Alert<br/>
    This is a machine-generated report. Do not reply.
  </p>

</div>
</body>
</html>"""
