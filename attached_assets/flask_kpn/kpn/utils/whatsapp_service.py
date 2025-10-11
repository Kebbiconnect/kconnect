"""
WhatsApp Integration Service for KPN System
Provides comprehensive WhatsApp messaging capabilities including:
- Individual WhatsApp messaging
- Group broadcasting
- Quick sharing from dashboards
- Integration with existing messaging system
"""

import os
import json
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from flask import current_app, url_for
from models import User, RoleType, ApprovalStatus


class WhatsAppService:
    """Comprehensive WhatsApp integration service for KPN"""
    
    def __init__(self):
        self.base_api_url = "https://api.whatsapp.com/send"
        self.business_api_url = os.environ.get('WHATSAPP_BUSINESS_API_URL', '')
        self.business_token = os.environ.get('WHATSAPP_BUSINESS_TOKEN', '')
        
    def generate_whatsapp_url(self, phone: str, message: str) -> str:
        """
        Generate WhatsApp URL for direct messaging
        
        Args:
            phone: Phone number with country code (e.g., +234801234567)
            message: Message text to send
            
        Returns:
            WhatsApp URL for opening conversation
        """
        # Clean phone number (remove spaces, hyphens, etc.)
        clean_phone = ''.join(filter(str.isdigit, phone.replace('+', '')))
        
        # Ensure Nigerian country code if not present
        if not clean_phone.startswith('234') and len(clean_phone) == 11:
            clean_phone = '234' + clean_phone[1:]  # Replace leading 0 with 234
        elif not clean_phone.startswith('234') and len(clean_phone) == 10:
            clean_phone = '234' + clean_phone
            
        # Encode message for URL
        encoded_message = quote_plus(message)
        
        return f"{self.base_api_url}?phone={clean_phone}&text={encoded_message}"
    
    def create_staff_message(self, sender_name: str, role: str, message: str, 
                           is_urgent: bool = False) -> str:
        """Create formatted message for staff communication"""
        
        urgency_prefix = "🚨 URGENT " if is_urgent else ""
        
        formatted_message = f"""
{urgency_prefix}📢 KPN Official Communication

From: {sender_name} ({role})

Message:
{message}

---
Kebbi Progressive Network (KPN)
Building a Better Kebbi State Together 🌟
        """.strip()
        
        return formatted_message
    
    def create_duty_reminder_message(self, user_name: str, duty_description: str, 
                                   due_date: str, days_overdue: int = 0) -> str:
        """Create formatted message for duty reminders"""
        
        if days_overdue > 0:
            status = f"⚠️ OVERDUE ({days_overdue} days)"
            urgency = "🚨 URGENT ACTION REQUIRED\n\n"
        else:
            status = "⏰ REMINDER"
            urgency = ""
            
        message = f"""
{urgency}{status} - Duty Reminder

Dear {user_name},

You have a pending duty that requires your attention:

📋 Duty: {duty_description}
📅 Due Date: {due_date}

Please complete this duty as soon as possible to maintain your active status in KPN.

If completed, please log in to the system to mark it as done.

---
KPN Management System
        """.strip()
        
        return message
    
    def create_announcement_message(self, title: str, content: str, 
                                  sender: str = "KPN Leadership") -> str:
        """Create formatted announcement message"""
        
        message = f"""
📢 KPN ANNOUNCEMENT

{title}

{content}

---
From: {sender}
Kebbi Progressive Network (KPN)
        """.strip()
        
        return message
    
    def get_user_whatsapp_contacts(self, role_types: List[RoleType]) -> List[Dict[str, Any]]:
        """
        Get WhatsApp-enabled contacts for bulk messaging
        
        Args:
            role_types: Filter by specific roles (required - must not be empty)
            
        Returns:
            List of contact dictionaries with name, phone, and role info
        """
        # Validate that role_types is not empty
        if not role_types:
            raise ValueError("role_types cannot be empty. This prevents accidental organization-wide broadcasts.")
        
        query = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.phone.isnot(None),
            User.phone != '',
            User.role_type.in_(role_types)
        )
            
        users = query.all()
        
        contacts = []
        for user in users:
            if user.phone:  # Double-check phone exists
                contacts.append({
                    'id': user.id,
                    'name': user.full_name,
                    'phone': user.phone,
                    'role': user.role_type.value if user.role_type else 'general_member',
                    'zone': user.zone.name if user.zone else 'Not assigned',
                    'lga': user.lga,
                    'ward': user.ward
                })
        
        return contacts
    
    def create_bulk_whatsapp_urls(self, contacts: List[Dict[str, Any]], 
                                message: str) -> List[Dict[str, str]]:
        """
        Create WhatsApp URLs for bulk messaging
        
        Args:
            contacts: List of contact dictionaries
            message: Message to send to all contacts
            
        Returns:
            List of dictionaries with contact info and WhatsApp URLs
        """
        bulk_urls = []
        
        for contact in contacts:
            whatsapp_url = self.generate_whatsapp_url(contact['phone'], message)
            
            bulk_urls.append({
                'name': contact['name'],
                'phone': contact['phone'], 
                'role': contact['role'],
                'zone': contact['zone'],
                'whatsapp_url': whatsapp_url
            })
            
        return bulk_urls
    
    def create_group_invite_message(self, group_name: str, group_description: str,
                                  admin_name: str, role_requirement: Optional[str] = None) -> str:
        """Create message for WhatsApp group invitations"""
        
        role_text = f"\nRole Requirement: {role_requirement}" if role_requirement else ""
        
        message = f"""
👥 KPN WhatsApp Group Invitation

Group: {group_name}

Description: {group_description}{role_text}

You are invited to join this official KPN WhatsApp group for important updates and communications.

Group Admin: {admin_name}

Click the link below to join:
[Group invite link will be provided separately]

---
Kebbi Progressive Network (KPN)
        """.strip()
        
        return message
    
    def create_emergency_broadcast_message(self, emergency_type: str, details: str,
                                         action_required: str, contact_info: str) -> str:
        """Create emergency broadcast message"""
        
        message = f"""
🚨 EMERGENCY ALERT - KPN

Type: {emergency_type}

Details: {details}

Action Required: {action_required}

Emergency Contact: {contact_info}

Please respond immediately or contact leadership.

---
KPN Emergency Communications
        """.strip()
        
        return message
    
    def validate_phone_number(self, phone: str) -> Dict[str, Any]:
        """
        Validate and format phone number for WhatsApp
        
        Args:
            phone: Phone number to validate
            
        Returns:
            Dictionary with validation results and formatted number
        """
        result = {
            'is_valid': False,
            'formatted': '',
            'original': phone,
            'errors': []
        }
        
        if not phone:
            result['errors'].append('Phone number is required')
            return result
            
        # Remove all non-digit characters except +
        cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        # Remove + if present
        if cleaned.startswith('+'):
            cleaned = cleaned[1:]
            
        # Validate length and format for Nigerian numbers
        if len(cleaned) == 11 and cleaned.startswith('0'):
            # Nigerian format: 08012345678 -> +2348012345678
            result['formatted'] = '234' + cleaned[1:]
            result['is_valid'] = True
        elif len(cleaned) == 10 and cleaned.startswith('8'):
            # Nigerian format: 8012345678 -> +2348012345678
            result['formatted'] = '234' + cleaned
            result['is_valid'] = True
        elif len(cleaned) == 13 and cleaned.startswith('234'):
            # Already in international format
            result['formatted'] = cleaned
            result['is_valid'] = True
        else:
            result['errors'].append('Invalid Nigerian phone number format')
            
        return result


class WhatsAppIntegration:
    """Integration helper for WhatsApp functionality in KPN system"""
    
    def __init__(self):
        self.service = WhatsAppService()
        
    def add_whatsapp_to_message_data(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add WhatsApp integration data to existing message data"""
        
        if 'recipient' in message_data and message_data['recipient'].get('phone'):
            # Add WhatsApp URL for individual messaging
            whatsapp_message = self.service.create_staff_message(
                sender_name=message_data.get('sender_name', 'KPN Admin'),
                role=message_data.get('sender_role', 'Administrator'), 
                message=message_data.get('body', ''),
                is_urgent=message_data.get('priority') == 'high'
            )
            
            message_data['whatsapp_url'] = self.service.generate_whatsapp_url(
                phone=message_data['recipient']['phone'],
                message=whatsapp_message
            )
            
        return message_data
    
    def get_role_based_contacts(self, current_user_role: RoleType) -> List[Dict[str, Any]]:
        """Get appropriate contacts based on user's role and hierarchy"""
        
        contacts = []
        
        if current_user_role in [RoleType.EXECUTIVE, RoleType.AUDITOR_GENERAL]:
            # Executives can message anyone
            contacts = self.service.get_user_whatsapp_contacts()
        elif current_user_role == RoleType.ZONAL_COORDINATOR:
            # Zonal coordinators can message their zone and below
            contacts = self.service.get_user_whatsapp_contacts([
                RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER
            ])
        elif current_user_role == RoleType.LGA_LEADER:
            # LGA leaders can message their LGA and below
            contacts = self.service.get_user_whatsapp_contacts([
                RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER
            ])
        else:
            # Ward leaders and general members can message peers
            contacts = self.service.get_user_whatsapp_contacts([
                RoleType.WARD_LEADER, RoleType.GENERAL_MEMBER
            ])
            
        return contacts