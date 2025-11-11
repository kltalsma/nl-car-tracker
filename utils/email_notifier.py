"""
Email notification utility for NL Car Tracker
Sends email alerts for top car matches and important updates
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional
import logging
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles email notifications for car matches"""
    
    def __init__(self, config_path='config.yaml'):
        """Initialize email notifier with configuration"""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.email_config = self.config.get('notifications', {}).get('email', {})
        self.enabled = self.email_config.get('enabled', False)
        
        if self.enabled:
            # Get credentials from environment variables
            self.smtp_server = self.email_config.get('smtp_server', 'smtp.gmail.com')
            self.smtp_port = self.email_config.get('smtp_port', 587)
            
            # Replace ${VAR} placeholders with environment variables
            from_email = self.email_config.get('from_email', '')
            from_password = self.email_config.get('from_password', '')
            
            self.from_email = self._resolve_env_var(from_email)
            self.from_password = self._resolve_env_var(from_password)
            self.to_email = self.email_config.get('to_email', '')
            
            self.notify_on_top_match = self.email_config.get('notify_on_top_match', True)
            self.notify_on_unavailable = self.email_config.get('notify_on_unavailable_preferred', True)
            self.min_score = self.email_config.get('min_score_for_notification', 85)
            
            logger.info(f"Email notifications enabled (to: {self.to_email})")
    
    def _resolve_env_var(self, value: str) -> str:
        """Resolve environment variable placeholders like ${VAR_NAME}"""
        if value.startswith('${') and value.endswith('}'):
            var_name = value[2:-1]
            return os.environ.get(var_name, '')
        return value
    
    def send_top_match_notification(self, car_data: Dict, score: int) -> bool:
        """
        Send email notification for a top car match
        
        Args:
            car_data: Dictionary containing car details
            score: Match score (0-100)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Email notifications disabled")
            return False
        
        if not self.notify_on_top_match:
            logger.debug("Top match notifications disabled")
            return False
        
        if score < self.min_score:
            logger.debug(f"Score {score} below minimum {self.min_score}, not sending email")
            return False
        
        try:
            # Build email content
            subject = f"🚗 Top Match Found: {car_data.get('year')} {car_data.get('make')} {car_data.get('model')} (Score: {score})"
            
            body = self._build_car_email_body(car_data, score)
            
            # Send email
            return self._send_email(subject, body, html=True)
            
        except Exception as e:
            logger.error(f"Failed to send top match notification: {e}")
            return False
    
    def send_unavailable_notification(self, car_data: Dict, reason: str = 'unknown') -> bool:
        """
        Send email notification when a preferred car becomes unavailable
        
        Args:
            car_data: Dictionary containing car details
            reason: Reason for unavailability
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled or not self.notify_on_unavailable:
            return False
        
        try:
            subject = f"⚠️ Car No Longer Available: {car_data.get('year')} {car_data.get('make')} {car_data.get('model')}"
            
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2 style="color: #e74c3c;">Car No Longer Available</h2>
                
                <p>A car you were tracking is no longer available:</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">{car_data.get('year')} {car_data.get('make')} {car_data.get('model')}</h3>
                    <p><strong>Price:</strong> €{car_data.get('price', 0):,.0f}</p>
                    <p><strong>Mileage:</strong> {car_data.get('mileage_km', 0):,} km</p>
                    <p><strong>Location:</strong> {car_data.get('location_city', 'Unknown')}</p>
                    <p><strong>Reason:</strong> {reason}</p>
                </div>
                
                <p><a href="{car_data.get('listing_url', '#')}" style="color: #3498db;">View Original Listing</a></p>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #7f8c8d; font-size: 12px;">
                    NL Car Tracker - {datetime.now().strftime('%Y-%m-%d %H:%M')}
                </p>
            </body>
            </html>
            """
            
            return self._send_email(subject, body, html=True)
            
        except Exception as e:
            logger.error(f"Failed to send unavailable notification: {e}")
            return False
    
    def _build_car_email_body(self, car_data: Dict, score: int) -> str:
        """Build HTML email body for car match notification"""
        
        # Calculate score bar color
        if score >= 90:
            score_color = "#27ae60"  # Green
        elif score >= 80:
            score_color = "#f39c12"  # Orange
        else:
            score_color = "#3498db"  # Blue
        
        # Format features
        features_html = ""
        if car_data.get('features'):
            features_list = car_data.get('features', [])
            if isinstance(features_list, list) and features_list:
                features_html = "<ul style='margin: 10px 0; padding-left: 20px;'>"
                for feature in features_list[:10]:  # Show first 10 features
                    features_html += f"<li>{feature}</li>"
                if len(features_list) > 10:
                    features_html += f"<li><em>...and {len(features_list) - 10} more</em></li>"
                features_html += "</ul>"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto;">
                <h2 style="color: {score_color}; border-bottom: 3px solid {score_color}; padding-bottom: 10px;">
                    🎯 Top Car Match Found!
                </h2>
                
                <div style="background: linear-gradient(135deg, {score_color}22 0%, {score_color}44 100%); 
                            padding: 20px; border-radius: 12px; margin: 20px 0; border-left: 5px solid {score_color};">
                    <h3 style="margin-top: 0; font-size: 24px;">
                        {car_data.get('year')} {car_data.get('make')} {car_data.get('model')}
                    </h3>
                    <div style="background: white; padding: 15px; border-radius: 8px; margin: 15px 0;">
                        <p style="margin: 5px 0;"><strong>Match Score:</strong> 
                            <span style="color: {score_color}; font-size: 20px; font-weight: bold;">{score}/100</span>
                        </p>
                        <div style="background: #e0e0e0; height: 8px; border-radius: 4px; margin: 10px 0;">
                            <div style="background: {score_color}; width: {score}%; height: 8px; border-radius: 4px;"></div>
                        </div>
                    </div>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="margin-top: 0; color: #2c3e50;">Vehicle Details</h4>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Price:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">€{car_data.get('price', 0):,.0f}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Mileage:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">{car_data.get('mileage_km', 0):,} km</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Year:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">{car_data.get('year', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Fuel Type:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">{car_data.get('fuel_type', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Range:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">{car_data.get('range_km', 'N/A')} km</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd;"><strong>Location:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #ddd; text-align: right;">{car_data.get('location_city', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Distance:</strong></td>
                            <td style="padding: 8px 0; text-align: right;">{car_data.get('distance_from_heerenveen_km', 'N/A')} km from Heerenveen</td>
                        </tr>
                    </table>
                </div>
                
                {f'<div style="background: #fff; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #ddd;"><h4 style="margin-top: 0; color: #2c3e50;">Key Features</h4>{features_html}</div>' if features_html else ''}
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{car_data.get('listing_url', '#')}" 
                       style="display: inline-block; background: {score_color}; color: white; 
                              padding: 15px 40px; text-decoration: none; border-radius: 8px; 
                              font-weight: bold; font-size: 16px;">
                        View Full Listing →
                    </a>
                </div>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <p style="margin: 0; color: #856404;">
                        <strong>⏰ Act Fast!</strong> Top matches like this don't last long. 
                        Contact the dealer soon to secure this vehicle.
                    </p>
                </div>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #7f8c8d; font-size: 12px; text-align: center;">
                    NL Car Tracker - Automated at {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
                    <a href="http://localhost:5001" style="color: #3498db;">View Dashboard</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return body
    
    def _send_email(self, subject: str, body: str, html: bool = True) -> bool:
        """
        Send an email using SMTP
        
        Args:
            subject: Email subject line
            body: Email body content
            html: Whether body is HTML (default: True)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.from_email or not self.from_password:
            logger.error("Email credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables.")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            
            # Attach body
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.from_email, self.from_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {self.to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test email configuration and connection"""
        if not self.enabled:
            logger.warning("Email notifications are disabled in config")
            return False
        
        try:
            subject = "🧪 NL Car Tracker - Test Email"
            body = """
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #27ae60;">✓ Email Notifications Working!</h2>
                <p>This is a test email from your NL Car Tracker.</p>
                <p>You will receive notifications here when top car matches are found.</p>
                <hr>
                <p style="color: #7f8c8d; font-size: 12px;">
                    Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </body>
            </html>
            """
            
            result = self._send_email(subject, body, html=True)
            
            if result:
                logger.info("✓ Test email sent successfully!")
            else:
                logger.error("✗ Failed to send test email")
            
            return result
            
        except Exception as e:
            logger.error(f"Email test failed: {e}")
            return False


if __name__ == "__main__":
    # Test the email notifier
    logging.basicConfig(level=logging.INFO)
    
    notifier = EmailNotifier()
    
    if notifier.enabled:
        print("Testing email configuration...")
        notifier.test_connection()
    else:
        print("Email notifications are disabled in config.yaml")
