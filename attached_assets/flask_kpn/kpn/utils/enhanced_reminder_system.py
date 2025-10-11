"""
Enhanced reminder system with email integration and auto-flagging
Comprehensive system for managing staff reminders, notifications, and status updates
"""

from models import db, User, DutyLog, StaffStatus, EngagementStatus, ApprovalStatus, RoleType
from utils.email_service import EmailService
from utils.staff_action_logger import create_reminder_for_missed_duty, auto_flag_inactive_staff
from datetime import datetime, timedelta
from flask import current_app, url_for
from typing import List, Dict, Optional
import json


class EnhancedReminderSystem:
    """Comprehensive reminder system with email integration"""
    
    def __init__(self):
        self.email_service = EmailService()
    
    def send_duty_reminder_email(self, user: User, duty: DutyLog, reminder_type: str = "overdue") -> bool:
        """Send email reminder for overdue or upcoming duties"""
        try:
            subject = ""
            html_content = ""
            
            # Prepare email content based on reminder type
            if reminder_type == "overdue":
                subject = f"⚠️ Overdue Duty Reminder - KPN {user.zone.name if user.zone else 'Organization'}"
                
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #d32f2f;">⚠️ Overdue Duty Reminder</h2>
                        
                        <p>Dear {user.full_name},</p>
                        
                        <p>This is a reminder that you have an overdue duty that requires your immediate attention:</p>
                        
                        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin: 20px 0;">
                            <h3 style="color: #856404; margin-top: 0;">Duty Details:</h3>
                            <p><strong>Description:</strong> {duty.duty_description}</p>
                            <p><strong>Due Date:</strong> {duty.due_date.strftime('%B %d, %Y') if duty.due_date else 'No specific date'}</p>
                            <p><strong>Days Overdue:</strong> {(datetime.utcnow().date() - duty.due_date.date()).days if duty.due_date else 'N/A'} days</p>
                        </div>
                        
                        <p><strong>Action Required:</strong> Please complete this duty as soon as possible to maintain your active status in the organization.</p>
                        
                        <p style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 5px; padding: 10px; color: #721c24;">
                            <strong>Warning:</strong> Continued delay may result in your status being changed to IRREGULAR or INACTIVE, which could affect your role responsibilities.
                        </p>
                        
                        <p>If you have completed this duty, please log in to the system and mark it as completed.</p>
                        
                        <p>Best regards,<br>
                        KPN Leadership Team<br>
                        {user.zone.name if user.zone else 'State'} Chapter</p>
                        
                        <hr style="margin-top: 30px;">
                        <p style="font-size: 12px; color: #666;">
                            This is an automated reminder from the KPN Management System. 
                            If you believe this is an error, please contact your supervisor.
                        </p>
                    </div>
                </body>
                </html>
                """
                
            elif reminder_type == "upcoming":
                subject = f"📅 Upcoming Duty Reminder - KPN {user.zone.name if user.zone else 'Organization'}"
                
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #1976d2;">📅 Upcoming Duty Reminder</h2>
                        
                        <p>Dear {user.full_name},</p>
                        
                        <p>This is a friendly reminder about an upcoming duty:</p>
                        
                        <div style="background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 5px; padding: 15px; margin: 20px 0;">
                            <h3 style="color: #1565c0; margin-top: 0;">Duty Details:</h3>
                            <p><strong>Description:</strong> {duty.duty_description}</p>
                            <p><strong>Due Date:</strong> {duty.due_date.strftime('%B %d, %Y') if duty.due_date else 'No specific date'}</p>
                            <p><strong>Days Remaining:</strong> {(duty.due_date.date() - datetime.utcnow().date()).days if duty.due_date else 'N/A'} days</p>
                        </div>
                        
                        <p>Please ensure you complete this duty on time to maintain your active status in the organization.</p>
                        
                        <p>Best regards,<br>
                        KPN Leadership Team<br>
                        {user.zone.name if user.zone else 'State'} Chapter</p>
                        
                        <hr style="margin-top: 30px;">
                        <p style="font-size: 12px; color: #666;">
                            This is an automated reminder from the KPN Management System.
                        </p>
                    </div>
                </body>
                </html>
                """
            
            # Send the email
            result = self.email_service.send_email(
                to=user.email,
                subject=subject,
                html=html_content
            )
            
            current_app.logger.info(f"Duty reminder email sent to {user.email} for duty: {duty.duty_description}")
            return result.get('success', False)
            
        except Exception as e:
            current_app.logger.error(f"Error sending duty reminder email to {user.email}: {e}")
            return False
    
    def send_status_change_notification(self, user: User, old_status: StaffStatus, new_status: StaffStatus) -> bool:
        """Send email notification when user status changes"""
        try:
            # Determine email styling based on status change
            if new_status == StaffStatus.INACTIVE:
                color = "#d32f2f"
                icon = "🚫"
                urgency = "URGENT"
            elif new_status == StaffStatus.IRREGULAR:
                color = "#f57c00"
                icon = "⚠️"
                urgency = "IMPORTANT"
            else:  # ACTIVE
                color = "#388e3c"
                icon = "✅"
                urgency = "NOTIFICATION"
            
            subject = f"{icon} {urgency}: Status Change - KPN {user.zone.name if user.zone else 'Organization'}"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: {color};">{icon} Status Change Notification</h2>
                    
                    <p>Dear {user.full_name},</p>
                    
                    <p>Your staff status has been automatically updated in the KPN Management System.</p>
                    
                    <div style="background-color: #f5f5f5; border-left: 4px solid {color}; padding: 15px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Status Change Details:</h3>
                        <p><strong>Previous Status:</strong> {old_status.value.replace('_', ' ').title()}</p>
                        <p><strong>New Status:</strong> {new_status.value.replace('_', ' ').title()}</p>
                        <p><strong>Change Date:</strong> {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')}</p>
                        <p><strong>Missed Duties:</strong> {user.missed_duties_count}</p>
                        <p><strong>Ignored Reminders:</strong> {user.ignored_reminders_count}</p>
                    </div>
                    
                    <h3>What This Means:</h3>
                    <ul>
            """
            
            if new_status == StaffStatus.INACTIVE:
                html_content += """
                        <li>Your account has been marked as INACTIVE due to prolonged inactivity</li>
                        <li>You may lose access to certain organizational functions</li>
                        <li>Immediate action is required to reactivate your status</li>
                        <li>Contact your supervisor to discuss reactivation steps</li>
                """
            elif new_status == StaffStatus.IRREGULAR:
                html_content += """
                        <li>Your account has been marked as IRREGULAR due to missed duties</li>
                        <li>This serves as a warning to improve your engagement</li>
                        <li>Complete pending duties to improve your status</li>
                        <li>Consistent completion of duties will restore ACTIVE status</li>
                """
            else:  # ACTIVE
                html_content += """
                        <li>Your account status has been restored to ACTIVE</li>
                        <li>You have full access to organizational functions</li>
                        <li>Continue your excellent engagement to maintain this status</li>
                """
            
            html_content += f"""
                    </ul>
                    
                    <p><strong>Next Steps:</strong> Log in to the system to view your current duties and take appropriate action.</p>
                    
                    <p>Best regards,<br>
                    KPN Leadership Team<br>
                    {user.zone.name if user.zone else 'State'} Chapter</p>
                    
                    <hr style="margin-top: 30px;">
                    <p style="font-size: 12px; color: #666;">
                        This is an automated notification from the KPN Management System.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Send the email
            result = self.email_service.send_email(
                to=user.email,
                subject=subject,
                html=html_content
            )
            
            current_app.logger.info(f"Status change notification sent to {user.email}: {old_status.value} -> {new_status.value}")
            return result.get('success', False)
            
        except Exception as e:
            current_app.logger.error(f"Error sending status change notification to {user.email}: {e}")
            return False
    
    def process_overdue_duties(self) -> Dict[str, int]:
        """Find and process all overdue duties, send reminders, and update statuses"""
        stats = {
            'overdue_found': 0,
            'reminders_sent': 0,
            'email_failures': 0,
            'status_changes': 0,
            'errors': 0
        }
        
        try:
            # Find overdue duties
            today = datetime.utcnow().date()
            overdue_duties = DutyLog.query.filter(
                DutyLog.due_date < datetime.utcnow(),
                DutyLog.completion_status == 'pending'
            ).all()
            
            stats['overdue_found'] = len(overdue_duties)
            
            # Process each overdue duty
            for duty in overdue_duties:
                try:
                    # Update duty status to overdue
                    duty.completion_status = 'overdue'
                    
                    # Get the user
                    user = duty.user
                    if not user or user.approval_status != ApprovalStatus.APPROVED:
                        continue
                    
                    # Send email reminder
                    email_sent = self.send_duty_reminder_email(user, duty, "overdue")
                    if email_sent:
                        stats['reminders_sent'] += 1
                    else:
                        stats['email_failures'] += 1
                    
                    # Increment missed duties count
                    user.increment_missed_duties()
                    
                    # Check if status needs to be updated
                    old_status = user.staff_status
                    user.update_staff_status()
                    
                    if old_status != user.staff_status:
                        stats['status_changes'] += 1
                        # Send status change notification
                        self.send_status_change_notification(user, old_status, user.staff_status)
                    
                except Exception as e:
                    stats['errors'] += 1
                    current_app.logger.error(f"Error processing overdue duty {duty.id}: {e}")
            
            db.session.commit()
            
            current_app.logger.info(
                f"Processed overdue duties: {stats['overdue_found']} found, "
                f"{stats['reminders_sent']} reminders sent, {stats['status_changes']} status changes"
            )
            
        except Exception as e:
            current_app.logger.error(f"Error in process_overdue_duties: {e}")
            db.session.rollback()
            stats['errors'] += 1
        
        return stats
    
    def send_upcoming_duty_reminders(self, days_ahead: int = 3) -> Dict[str, int]:
        """Send reminders for upcoming duties"""
        stats = {
            'upcoming_found': 0,
            'reminders_sent': 0,
            'email_failures': 0,
            'errors': 0
        }
        
        try:
            # Find duties due in the next few days
            today = datetime.utcnow()
            target_date = today + timedelta(days=days_ahead)
            
            upcoming_duties = DutyLog.query.filter(
                DutyLog.due_date.between(target_date.replace(hour=0, minute=0, second=0), 
                                       target_date.replace(hour=23, minute=59, second=59)),
                DutyLog.completion_status == 'pending'
            ).all()
            
            stats['upcoming_found'] = len(upcoming_duties)
            
            for duty in upcoming_duties:
                try:
                    user = duty.user
                    if not user or user.approval_status != ApprovalStatus.APPROVED:
                        continue
                    
                    # Send upcoming reminder email
                    email_sent = self.send_duty_reminder_email(user, duty, "upcoming")
                    if email_sent:
                        stats['reminders_sent'] += 1
                    else:
                        stats['email_failures'] += 1
                        
                except Exception as e:
                    stats['errors'] += 1
                    current_app.logger.error(f"Error sending upcoming reminder for duty {duty.id}: {e}")
            
            current_app.logger.info(
                f"Sent upcoming duty reminders: {stats['upcoming_found']} found, "
                f"{stats['reminders_sent']} reminders sent"
            )
            
        except Exception as e:
            current_app.logger.error(f"Error in send_upcoming_duty_reminders: {e}")
            stats['errors'] += 1
        
        return stats
    
    def run_comprehensive_staff_review(self) -> Dict[str, any]:
        """Run comprehensive review of all staff members"""
        stats = {
            'total_staff': 0,
            'status_changes': 0,
            'notifications_sent': 0,
            'overdue_processed': 0,
            'upcoming_reminders': 0,
            'email_failures': 0,
            'errors': 0,
            'details': []
        }
        
        try:
            # Process overdue duties first
            overdue_stats = self.process_overdue_duties()
            stats['overdue_processed'] = overdue_stats['overdue_found']
            stats['email_failures'] += overdue_stats['email_failures']
            
            # Send upcoming reminders
            upcoming_stats = self.send_upcoming_duty_reminders()
            stats['upcoming_reminders'] = upcoming_stats['reminders_sent']
            stats['email_failures'] += upcoming_stats['email_failures']
            
            # Run auto-flagging system
            flagging_stats = auto_flag_inactive_staff()
            stats['total_staff'] = flagging_stats['total_checked']
            stats['status_changes'] = flagging_stats['flagged_inactive'] + flagging_stats['flagged_irregular']
            
            # Note: Status change notifications are handled in auto_flag_inactive_staff function
            # Future enhancement: Track status changes for immediate notifications
            
            current_app.logger.info(
                f"Comprehensive staff review completed: "
                f"{stats['total_staff']} staff checked, {stats['status_changes']} status changes, "
                f"{stats['overdue_processed']} overdue processed, {stats['upcoming_reminders']} upcoming reminders"
            )
            
        except Exception as e:
            current_app.logger.error(f"Error in run_comprehensive_staff_review: {e}")
            stats['errors'] += 1
        
        return stats
    
    def create_custom_reminder(self, user: User, duty_description: str, 
                             due_date: Optional[datetime] = None, send_email: bool = True) -> Optional[DutyLog]:
        """Create a custom reminder with optional email notification"""
        try:
            # Create the reminder duty
            duty_log = create_reminder_for_missed_duty(user, duty_description, due_date or datetime.utcnow())
            
            if duty_log and send_email:
                # Send immediate email notification
                reminder_type = "upcoming" if due_date and due_date > datetime.utcnow() else "overdue"
                self.send_duty_reminder_email(user, duty_log, reminder_type)
            
            return duty_log
            
        except Exception as e:
            current_app.logger.error(f"Error creating custom reminder for {user.full_name if user else 'unknown'}: {e}")
            return None
    
    def send_bulk_announcements(self, staff_roles: List[RoleType], subject: str, 
                               message: str, html_message: Optional[str] = None) -> Dict[str, int]:
        """Send bulk email announcements to specific staff roles"""
        stats = {
            'recipients_found': 0,
            'emails_sent': 0,
            'email_failures': 0,
            'errors': 0
        }
        
        try:
            # Get staff members with specified roles
            if staff_roles:
                staff_members = User.query.filter(
                    User.approval_status == ApprovalStatus.APPROVED,
                    User.role_type.in_(staff_roles)
                ).all()
            else:
                staff_members = User.query.filter(
                    User.approval_status == ApprovalStatus.APPROVED
                ).all()
            
            stats['recipients_found'] = len(staff_members)
            
            for user in staff_members:
                try:
                    # Prepare personalized message
                    if html_message:
                        personalized_html = html_message
                    else:
                        formatted_message = message.replace('\n', '<br>')
                        personalized_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                                <h2>📢 Announcement</h2>
                                <p>Dear {user.full_name},</p>
                                <div style="background-color: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 20px 0;">
                                    {formatted_message}
                                </div>
                                <p>Best regards,<br>KPN Leadership Team</p>
                            </div>
                        </body>
                        </html>
                        """
                    
                    # Send email
                    result = self.email_service.send_email(
                        to=user.email,
                        subject=subject,
                        text=message,
                        html=personalized_html
                    )
                    
                    if result.get('success', False):
                        stats['emails_sent'] += 1
                    else:
                        stats['email_failures'] += 1
                        
                except Exception as e:
                    stats['errors'] += 1
                    current_app.logger.error(f"Error sending announcement to {user.email}: {e}")
            
            current_app.logger.info(
                f"Bulk announcement sent: {stats['emails_sent']} successful, "
                f"{stats['email_failures']} failed out of {stats['recipients_found']} recipients"
            )
            
        except Exception as e:
            current_app.logger.error(f"Error in send_bulk_announcements: {e}")
            stats['errors'] += 1
        
        return stats


# Global instance for easy access
reminder_system = EnhancedReminderSystem()


def daily_reminder_job():
    """Daily scheduled job for processing reminders and status updates"""
    try:
        current_app.logger.info("Starting daily reminder job...")
        
        # Run comprehensive staff review
        stats = reminder_system.run_comprehensive_staff_review()
        
        current_app.logger.info(f"Daily reminder job completed: {stats}")
        return stats
        
    except Exception as e:
        current_app.logger.error(f"Error in daily_reminder_job: {e}")
        return {'error': str(e)}


def send_weekly_summary_reports():
    """Send weekly summary reports to leadership"""
    try:
        current_app.logger.info("Sending weekly summary reports...")
        
        # Get leadership members
        leadership_roles = [RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.AUDITOR_GENERAL]
        leadership = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type.in_(leadership_roles)
        ).all()
        
        # Generate summary statistics
        total_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER
        ).count()
        
        active_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.ACTIVE
        ).count()
        
        irregular_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.IRREGULAR
        ).count()
        
        inactive_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.staff_status == StaffStatus.INACTIVE
        ).count()
        
        # Get overdue duties count
        overdue_duties = DutyLog.query.filter(
            DutyLog.due_date < datetime.utcnow().date(),
            DutyLog.completion_status.in_(['pending', 'overdue'])
        ).count()
        
        # Create summary report
        subject = f"📊 Weekly Staff Summary Report - {datetime.utcnow().strftime('%B %d, %Y')}"
        
        summary_stats = {
            'total_staff': total_staff,
            'active_staff': active_staff,
            'irregular_staff': irregular_staff,
            'inactive_staff': inactive_staff,
            'overdue_duties': overdue_duties,
            'activity_rate': round((active_staff / total_staff * 100) if total_staff > 0 else 0, 1)
        }
        
        # Send to each leadership member
        stats = reminder_system.send_bulk_announcements(
            staff_roles=leadership_roles,
            subject=subject,
            message=f"""
Weekly Staff Summary Report

Total Staff Members: {total_staff}
Active Staff: {active_staff} ({summary_stats['activity_rate']}%)
Irregular Staff: {irregular_staff}
Inactive Staff: {inactive_staff}
Overdue Duties: {overdue_duties}

This automated report provides an overview of staff engagement and performance.
""",
            html_message=f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1976d2;">📊 Weekly Staff Summary Report</h2>
        <p style="color: #666;">{datetime.utcnow().strftime('%B %d, %Y')}</p>
        
        <div style="background-color: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #343a40;">Staff Overview</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #dee2e6;">
                    <td style="padding: 8px 0; font-weight: bold;">Total Staff Members:</td>
                    <td style="padding: 8px 0; text-align: right;">{total_staff}</td>
                </tr>
                <tr style="border-bottom: 1px solid #dee2e6;">
                    <td style="padding: 8px 0; color: #28a745;">Active Staff:</td>
                    <td style="padding: 8px 0; text-align: right; color: #28a745;">{active_staff} ({summary_stats['activity_rate']}%)</td>
                </tr>
                <tr style="border-bottom: 1px solid #dee2e6;">
                    <td style="padding: 8px 0; color: #ffc107;">Irregular Staff:</td>
                    <td style="padding: 8px 0; text-align: right; color: #ffc107;">{irregular_staff}</td>
                </tr>
                <tr style="border-bottom: 1px solid #dee2e6;">
                    <td style="padding: 8px 0; color: #dc3545;">Inactive Staff:</td>
                    <td style="padding: 8px 0; text-align: right; color: #dc3545;">{inactive_staff}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #dc3545;">Overdue Duties:</td>
                    <td style="padding: 8px 0; text-align: right; color: #dc3545;">{overdue_duties}</td>
                </tr>
            </table>
        </div>
        
        <p>This automated report provides an overview of staff engagement and performance.</p>
        <p>Please review any concerning trends and take appropriate action.</p>
        
        <hr style="margin-top: 30px;">
        <p style="font-size: 12px; color: #666;">
            Generated automatically by the KPN Management System
        </p>
    </div>
</body>
</html>
"""
        )
        
        current_app.logger.info(f"Weekly summary reports sent: {stats}")
        return stats
        
    except Exception as e:
        current_app.logger.error(f"Error sending weekly summary reports: {e}")
        return {'error': str(e)}