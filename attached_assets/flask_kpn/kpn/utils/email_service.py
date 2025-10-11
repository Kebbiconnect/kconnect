# Email service using Replit Mail integration
# Based on blueprint:replitmail integration

import os
import json
import requests
from typing import Union, List, Optional, Dict, Any
from flask import current_app

class EmailService:
    """Email service using Replit Mail OpenInt API integration"""
    
    def __init__(self):
        self.api_endpoint = "https://connectors.replit.com/api/v2/mailer/send"
    
    def _get_auth_token(self) -> str:
        """Get authentication token for Replit environment"""
        repl_identity = os.environ.get('REPL_IDENTITY')
        web_repl_renewal = os.environ.get('WEB_REPL_RENEWAL')
        
        if repl_identity:
            return f"repl {repl_identity}"
        elif web_repl_renewal:
            return f"depl {web_repl_renewal}"
        else:
            raise Exception("No authentication token found. Please ensure you're running in Replit environment.")
    
    def send_email(self, 
                   to: str, 
                   subject: str, 
                   text: Optional[str] = None, 
                   html: Optional[str] = None,
                   cc: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Send email using Replit Mail service
        
        Args:
            to: Recipient email address
            subject: Email subject
            text: Plain text body (optional)
            html: HTML body (optional)
            cc: CC recipients (optional)
            
        Returns:
            Dict with sending results
        """
        try:
            auth_token = self._get_auth_token()
            
            # Prepare email payload
            payload = {
                "to": to,
                "subject": subject
            }
            
            if text:
                payload["text"] = text
            if html:
                payload["html"] = html
            if cc:
                # Handle cc as string or list
                if isinstance(cc, str):
                    payload["cc"] = [cc]
                else:
                    payload["cc"] = cc
            
            # Send request to Replit Mail API
            headers = {
                "Content-Type": "application/json",
                "X_REPLIT_TOKEN": auth_token
            }
            
            response = requests.post(
                self.api_endpoint,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if not response.ok:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_message = error_data.get('message', f'HTTP {response.status_code}: Failed to send email')
                raise Exception(error_message)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Email service request failed: {str(e)}")
            raise Exception(f"Failed to send email: {str(e)}")
        except Exception as e:
            current_app.logger.error(f"Email service error: {str(e)}")
            raise
    
    def send_password_reset_email(self, to: str, reset_link: str, user_name: str) -> Dict[str, Any]:
        """
        Send password reset email with styled template
        
        Args:
            to: User's email address
            reset_link: Password reset link
            user_name: User's full name
            
        Returns:
            Email sending result
        """
        subject = "KPN - Password Reset Request"
        
        # HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Reset - KPN</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; }}
                .header {{ background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%); color: white; padding: 30px 20px; text-align: center; }}
                .content {{ padding: 30px 20px; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%); color: white; text-decoration: none; padding: 12px 30px; border-radius: 6px; font-weight: bold; margin: 20px 0; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 14px; }}
                .warning {{ background-color: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 6px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">KPN</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Kebbi Progressive Network</p>
                    <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">One Voice, One Change</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2E7D32; margin-bottom: 20px;">Password Reset Request</h2>
                    
                    <p>Dear <strong>{user_name}</strong>,</p>
                    
                    <p>We received a request to reset your password for your KPN account. If you made this request, please click the button below to reset your password:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" class="button">Reset My Password</a>
                    </div>
                    
                    <div class="warning">
                        <strong>Important Security Information:</strong>
                        <ul style="margin: 10px 0;">
                            <li>This link will expire in 1 hour for security reasons</li>
                            <li>If you didn't request this password reset, please ignore this email</li>
                            <li>Your password will not be changed unless you click the link above</li>
                        </ul>
                    </div>
                    
                    <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #4CAF50; font-family: monospace; background-color: #f8f9fa; padding: 10px; border-radius: 4px;">{reset_link}</p>
                    
                    <p>If you need help or have questions, please contact our support team.</p>
                    
                    <p>Best regards,<br><strong>The KPN Team</strong></p>
                </div>
                
                <div class="footer">
                    <p><strong>Kebbi Progressive Network (KPN)</strong></p>
                    <p>Building a progressive Kebbi State together</p>
                    <p style="font-size: 12px; margin-top: 15px;">
                        This is an automated message. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version for email clients that don't support HTML
        text_content = f"""
        KPN - Password Reset Request
        
        Dear {user_name},
        
        We received a request to reset your password for your KPN account.
        
        To reset your password, please visit this link:
        {reset_link}
        
        Important:
        - This link will expire in 1 hour for security reasons
        - If you didn't request this password reset, please ignore this email
        - Your password will not be changed unless you visit the link above
        
        If you need help, please contact our support team.
        
        Best regards,
        The KPN Team
        
        ---
        Kebbi Progressive Network (KPN)
        Building a progressive Kebbi State together
        """
        
        return self.send_email(
            to=to,
            subject=subject,
            html=html_content,
            text=text_content
        )

# Create global instance
email_service = EmailService()