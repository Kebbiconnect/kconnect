from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, Message, RoleType, Zone, ApprovalStatus
from datetime import datetime
import json

messages = Blueprint('messages', __name__)

@messages.route('/inbox')
@login_required
def inbox():
    """Display user's inbox with received messages"""
    # Get received messages (unarchived)
    received_messages = Message.query.filter_by(
        recipient_id=current_user.id,
        is_archived=False
    ).order_by(Message.created_at.desc()).all()
    
    # Count unread messages
    unread_count = Message.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_archived=False
    ).count()
    
    return render_template('messages/inbox.html', 
                         messages=received_messages,
                         unread_count=unread_count)

@messages.route('/sent')
@login_required
def sent():
    """Display user's sent messages"""
    sent_messages = Message.query.filter_by(
        sender_id=current_user.id
    ).order_by(Message.created_at.desc()).all()
    
    return render_template('messages/sent.html', messages=sent_messages)

@messages.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    """Compose and send a new message"""
    if request.method == 'POST':
        try:
            recipient_id = request.form.get('recipient_id')
            subject = request.form.get('subject', '').strip()
            body = request.form.get('body', '').strip()
            priority = request.form.get('priority', 'normal')
            
            # Validation
            if not recipient_id:
                flash('Please select a recipient.', 'error')
                return redirect(url_for('messages.compose'))
            
            if not subject:
                flash('Subject is required.', 'error')
                return redirect(url_for('messages.compose'))
            
            if not body:
                flash('Message body is required.', 'error')
                return redirect(url_for('messages.compose'))
            
            # Check if recipient exists and is not the sender
            recipient = User.query.get(recipient_id)
            if not recipient:
                flash('Invalid recipient selected.', 'error')
                return redirect(url_for('messages.compose'))
            
            if recipient.id == current_user.id:
                flash('You cannot send a message to yourself.', 'error')
                return redirect(url_for('messages.compose'))
            
            # Create new message
            new_message = Message(
                sender_id=current_user.id,
                recipient_id=recipient_id,
                subject=subject,
                body=body,
                priority=priority,
                message_type='personal'
            )
            
            db.session.add(new_message)
            db.session.commit()
            
            flash(f'Message sent successfully to {recipient.full_name}!', 'success')
            return redirect(url_for('messages.sent'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while sending the message. Please try again.', 'error')
    
    # Get all users except current user for recipient selection
    all_users = User.query.filter(User.id != current_user.id).order_by(User.full_name).all()
    
    return render_template('messages/compose.html', users=all_users)

@messages.route('/view/<int:message_id>')
@login_required
def view_message(message_id):
    """View a specific message"""
    message = Message.query.get_or_404(message_id)
    
    # Check if user has permission to view this message
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        flash('You do not have permission to view this message.', 'error')
        return redirect(url_for('messages.inbox'))
    
    # Mark as read if recipient is viewing
    if message.recipient_id == current_user.id and not message.is_read:
        message.mark_as_read()
        db.session.commit()
    
    return render_template('messages/view.html', message=message)

@messages.route('/reply/<int:message_id>', methods=['GET', 'POST'])
@login_required
def reply(message_id):
    """Reply to a message"""
    original_message = Message.query.get_or_404(message_id)
    
    # Check if user can reply (must be recipient of original message)
    if original_message.recipient_id != current_user.id:
        flash('You can only reply to messages sent to you.', 'error')
        return redirect(url_for('messages.inbox'))
    
    if request.method == 'POST':
        try:
            body = request.form.get('body', '').strip()
            priority = request.form.get('priority', 'normal')
            
            if not body:
                flash('Reply message is required.', 'error')
                return render_template('messages/reply.html', original_message=original_message)
            
            # Create reply message
            reply_subject = f"Re: {original_message.subject}" if not original_message.subject.startswith('Re:') else original_message.subject
            
            reply_message = Message(
                sender_id=current_user.id,
                recipient_id=original_message.sender_id,
                subject=reply_subject,
                body=body,
                priority=priority,
                message_type='personal'
            )
            
            db.session.add(reply_message)
            db.session.commit()
            
            flash('Reply sent successfully!', 'success')
            return redirect(url_for('messages.sent'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while sending the reply. Please try again.', 'error')
    
    return render_template('messages/reply.html', original_message=original_message)

@messages.route('/delete/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    """Archive/delete a message"""
    message = Message.query.get_or_404(message_id)
    
    # Check permission
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        flash('You do not have permission to delete this message.', 'error')
        return redirect(url_for('messages.inbox'))
    
    try:
        message.is_archived = True
        db.session.commit()
        flash('Message archived successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while archiving the message.', 'error')
    
    return redirect(request.referrer or url_for('messages.inbox'))

@messages.route('/unread-count')
@login_required
def unread_count():
    """Get unread message count for current user (AJAX endpoint)"""
    count = Message.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_archived=False
    ).count()
    
    return jsonify({'unread_count': count})

@messages.route('/whatsapp-share')
@login_required
def whatsapp_share():
    """WhatsApp sharing functionality"""
    # Get sharing content from query parameters
    title = request.args.get('title', 'Check this out from KPN Kebbi!')
    url = request.args.get('url', request.url_root)
    text = request.args.get('text', '')
    
    # Prepare WhatsApp share URL
    whatsapp_text = f"{title}\n{text}\n{url}"
    whatsapp_url = f"https://wa.me/?text={whatsapp_text}"
    
    return render_template('messages/whatsapp_share.html', 
                         whatsapp_url=whatsapp_url,
                         title=title,
                         text=text,
                         url=url)

@messages.route('/share-profile')
@login_required  
def share_profile():
    """Share user profile via WhatsApp"""
    profile_url = url_for('core.home', _external=True)  # Could be specific profile URL
    share_text = f"Hello! I'm {current_user.full_name}, a member of Kebbi Progressive Network (KPN). Join us in building a better Kebbi State!"
    
    whatsapp_url = f"https://wa.me/?text={share_text}\n{profile_url}"
    
    return redirect(whatsapp_url)

@messages.route('/bulk-whatsapp', methods=['GET', 'POST'])
@login_required
def bulk_whatsapp():
    """Bulk WhatsApp messaging interface - restricted to authorized roles"""
    from utils.whatsapp_service import WhatsAppService
    
    # Check if user has permission for bulk messaging
    authorized_roles = [RoleType.EXECUTIVE, RoleType.AUDITOR_GENERAL, RoleType.ZONAL_COORDINATOR]
    if current_user.role_type not in authorized_roles:
        flash('You do not have permission to access bulk WhatsApp messaging.', 'error')
        return redirect(url_for('messages.inbox'))
    
    whatsapp_service = WhatsAppService()
    
    if request.method == 'POST':
        try:
            # Get form data
            message_title = request.form.get('title', '').strip()
            message_body = request.form.get('body', '').strip()
            selected_roles = request.form.getlist('roles')
            is_urgent = request.form.get('urgent') == 'on'
            
            if not message_title or not message_body:
                flash('Title and message are required.', 'error')
                return redirect(url_for('messages.bulk_whatsapp'))
            
            # Validate that at least one role is selected
            if not selected_roles:
                flash('Please select at least one recipient role.', 'error')
                return redirect(url_for('messages.bulk_whatsapp'))
            
            # Convert role strings to RoleType enums
            role_types = []
            invalid_roles = []
            for role_str in selected_roles:
                try:
                    role_types.append(RoleType(role_str))
                except ValueError:
                    invalid_roles.append(role_str)
            
            # Check if any valid roles were found
            if not role_types:
                flash(f'Invalid role selections: {", ".join(invalid_roles)}. Please select valid roles.', 'error')
                return redirect(url_for('messages.bulk_whatsapp'))
            
            # Warn about invalid roles if some were found
            if invalid_roles:
                flash(f'Ignored invalid roles: {", ".join(invalid_roles)}', 'warning')
            
            # Get contacts based on selected roles (will not be empty due to validation)
            contacts = whatsapp_service.get_user_whatsapp_contacts(role_types)
            
            if not contacts:
                role_names = [role.value.replace('_', ' ').title() for role in role_types]
                flash(f'No contacts found with phone numbers for the selected roles: {", ".join(role_names)}.', 'warning')
                return redirect(url_for('messages.bulk_whatsapp'))
            
            # Create formatted message
            formatted_message = whatsapp_service.create_announcement_message(
                title=message_title,
                content=message_body,
                sender=f"{current_user.full_name} ({current_user.role_type.value.replace('_', ' ').title() if current_user.role_type else 'KPN Member'})"
            )
            
            if is_urgent:
                formatted_message = f"🚨 URGENT\n\n{formatted_message}"
            
            # Generate WhatsApp URLs for all contacts
            bulk_urls = whatsapp_service.create_bulk_whatsapp_urls(contacts, formatted_message)
            
            return render_template('messages/bulk_whatsapp_results.html', 
                                 bulk_urls=bulk_urls,
                                 message_title=message_title,
                                 message_body=message_body,
                                 total_recipients=len(bulk_urls))
            
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
    
    # Get available role types dynamically from RoleType enum
    available_roles = []
    for role in RoleType:
        role_display_name = role.value.replace('_', ' ').title() + ('s' if not role.value.endswith('s') else '')
        available_roles.append((role.value, role_display_name))
    
    return render_template('messages/bulk_whatsapp.html', available_roles=available_roles)

@messages.route('/whatsapp-direct/<int:user_id>')
@login_required
def whatsapp_direct(user_id):
    """Generate direct WhatsApp message to a specific user"""
    from utils.whatsapp_service import WhatsAppService
    
    target_user = User.query.get_or_404(user_id)
    
    # Basic permission check - users can only WhatsApp message people they can already message
    # This prevents unauthorized access to phone numbers
    if target_user.id == current_user.id:
        flash('Cannot send WhatsApp message to yourself.', 'error')
        return redirect(request.referrer or url_for('messages.inbox'))
    
    if not target_user.phone:
        flash('This user does not have a phone number on file.', 'error')
        return redirect(request.referrer or url_for('messages.inbox'))
    
    # Get message content from query parameters
    subject = request.args.get('subject', 'KPN Communication')
    body = request.args.get('body', 'Hello from KPN!')
    
    whatsapp_service = WhatsAppService()
    
    # Create formatted message
    formatted_message = whatsapp_service.create_staff_message(
        sender_name=current_user.full_name,
        role=current_user.role_type.value.replace('_', ' ').title() if current_user.role_type else 'KPN Member',
        message=f"Subject: {subject}\n\n{body}",
        is_urgent=request.args.get('urgent') == 'true'
    )
    
    # Generate WhatsApp URL
    whatsapp_url = whatsapp_service.generate_whatsapp_url(target_user.phone, formatted_message)
    
    return redirect(whatsapp_url)

@messages.route('/emergency-broadcast', methods=['GET', 'POST'])
@login_required
def emergency_broadcast():
    """Emergency WhatsApp broadcasting - restricted to executives only"""
    
    # Check if user has permission for emergency broadcasts
    if current_user.role_type not in [RoleType.EXECUTIVE, RoleType.AUDITOR_GENERAL]:
        flash('You do not have permission to send emergency broadcasts.', 'error')
        return redirect(url_for('messages.inbox'))
    
    if request.method == 'POST':
        from utils.whatsapp_service import WhatsAppService
        
        whatsapp_service = WhatsAppService()
        
        try:
            emergency_type = request.form.get('emergency_type', '').strip()
            details = request.form.get('details', '').strip()
            action_required = request.form.get('action_required', '').strip()
            contact_info = request.form.get('contact_info', current_user.phone or 'KPN Leadership')
            
            if not all([emergency_type, details, action_required]):
                flash('All fields are required for emergency broadcasts.', 'error')
                return render_template('messages/emergency_broadcast.html')
            
            # Create emergency message
            emergency_message = whatsapp_service.create_emergency_broadcast_message(
                emergency_type=emergency_type,
                details=details,
                action_required=action_required,
                contact_info=contact_info
            )
            
            # Get all approved users with phone numbers
            contacts = whatsapp_service.get_user_whatsapp_contacts()
            
            if not contacts:
                flash('No contacts available for emergency broadcast.', 'warning')
                return render_template('messages/emergency_broadcast.html')
            
            # Generate WhatsApp URLs
            bulk_urls = whatsapp_service.create_bulk_whatsapp_urls(contacts, emergency_message)
            
            return render_template('messages/emergency_broadcast_results.html',
                                 bulk_urls=bulk_urls,
                                 emergency_type=emergency_type,
                                 total_recipients=len(bulk_urls))
            
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
    
    return render_template('messages/emergency_broadcast.html')

@messages.route('/send-zone-message', methods=['POST'])
@login_required
def send_zone_message():
    """Send message to all users in a specific zone"""
    # Check permissions - only admin and executives can send zone messages
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'success': False, 'message': 'Access denied. Only admin and executives can send zone messages.'}), 403
    
    try:
        data = request.get_json()
        zone_id = data.get('zone_id')
        message_text = data.get('message', '').strip()
        
        if not zone_id:
            return jsonify({'success': False, 'message': 'Zone ID is required.'}), 400
        
        if not message_text:
            return jsonify({'success': False, 'message': 'Message text is required.'}), 400
        
        # Get the zone
        zone = Zone.query.get(zone_id)
        if not zone:
            return jsonify({'success': False, 'message': 'Zone not found.'}), 404
        
        # Get all approved users in the zone
        zone_users = User.query.filter_by(
            zone_id=zone_id,
            approval_status=ApprovalStatus.APPROVED
        ).all()
        
        if not zone_users:
            return jsonify({'success': False, 'message': f'No approved users found in {zone.name}.'}), 404
        
        # Create messages for each user in the zone
        messages_created = 0
        for user in zone_users:
            if user.id != current_user.id:  # Don't send to self
                new_message = Message(
                    sender_id=current_user.id,
                    recipient_id=user.id,
                    subject=f'Zone Message - {zone.name}',
                    body=message_text,
                    message_type='announcement',
                    priority='normal'
                )
                db.session.add(new_message)
                messages_created += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Message sent successfully to {messages_created} users in {zone.name}.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500

@messages.route('/send-bulk-zone-message', methods=['POST'])
@login_required
def send_bulk_zone_message():
    """Send message to all users in all zones"""
    # Check permissions - only admin can send bulk zone messages
    if current_user.role_type != RoleType.ADMIN:
        return jsonify({'success': False, 'message': 'Access denied. Only admin can send bulk zone messages.'}), 403
    
    try:
        data = request.get_json()
        message_text = data.get('message', '').strip()
        
        if not message_text:
            return jsonify({'success': False, 'message': 'Message text is required.'}), 400
        
        # Get all approved users across all zones
        all_users = User.query.filter_by(approval_status=ApprovalStatus.APPROVED).all()
        
        if not all_users:
            return jsonify({'success': False, 'message': 'No approved users found.'}), 404
        
        # Create messages for each approved user (excluding self)
        messages_created = 0
        zones_count = Zone.query.count()
        
        for user in all_users:
            if user.id != current_user.id:  # Don't send to self
                new_message = Message(
                    sender_id=current_user.id,
                    recipient_id=user.id,
                    subject='Bulk Zone Message - All Zones',
                    body=message_text,
                    message_type='announcement',
                    priority='normal'
                )
                db.session.add(new_message)
                messages_created += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Bulk message sent successfully to {messages_created} users across {zones_count} zones.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500