from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import *
from utils.facebook_api import (
    track_campaign_engagement, bulk_check_staff_engagement, 
    get_campaign_engagement_report, send_engagement_reminders
)
from datetime import datetime, timedelta

campaigns = Blueprint('campaigns', __name__)

@campaigns.route('/')
def list_campaigns():
    campaigns = Campaign.query.filter_by(published=True).order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns/list.html', campaigns=campaigns)

@campaigns.route('/<int:campaign_id>')
def view_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    if not campaign.published:
        flash('Campaign not found.', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
    
    return render_template('campaigns/view.html', campaign=campaign)

@campaigns.route('/manage')
@login_required
def manage():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns/manage.html', campaigns=campaigns)

@campaigns.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    # Allow ADMIN, EXECUTIVE, and Publicity Officers to create campaigns
    allowed_roles = [RoleType.ADMIN, RoleType.EXECUTIVE]
    allowed_publicity_roles = ['Publicity', 'Assistant Director of Media & Publicity', 'Director of Media & Publicity']
    
    if current_user.role_type not in allowed_roles:
        if not (current_user.role_type in [RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.EXECUTIVE] and 
                current_user.role_title in allowed_publicity_roles):
            flash('Access denied.', 'error')
            return redirect(url_for('core.home'))
    
    if request.method == 'POST':
        # Extract Facebook post ID from URL if provided
        facebook_post_url = request.form.get('facebook_post_url', '').strip()
        facebook_post_id = None
        if facebook_post_url:
            # Extract post ID from Facebook URL
            # Format: https://www.facebook.com/page/posts/123456789
            # or https://www.facebook.com/123456789/posts/987654321
            import re
            post_id_match = re.search(r'/posts/([0-9]+)', facebook_post_url)
            if post_id_match:
                facebook_post_id = post_id_match.group(1)
        
        # Publicity officers cannot directly publish - needs approval
        can_publish_directly = current_user.role_type in [RoleType.ADMIN] or \
                              (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity')
        
        campaign = Campaign(
            title=request.form['title'],
            content=request.form['content'],
            author_id=current_user.id,
            published=False,  # Always False initially - requires approval
            featured=request.form.get('featured') == 'on' if can_publish_directly else False,
            facebook_post_url=facebook_post_url,
            facebook_post_id=facebook_post_id,
            engagement_required=request.form.get('engagement_required') == 'on',
            approval_status='approved' if can_publish_directly else 'pending'
        )
        
        # Auto-approve and publish if user has direct publishing rights
        if can_publish_directly:
            campaign.published = request.form.get('published') == 'on'
            campaign.approved_by_id = current_user.id
            campaign.approved_at = datetime.utcnow()
        
        # Set engagement deadline if engagement is required
        if campaign.engagement_required:
            days_deadline = request.form.get('engagement_deadline_days', 7)
            try:
                days = int(days_deadline)
                campaign.engagement_deadline = datetime.utcnow() + timedelta(days=days)
            except (ValueError, TypeError):
                campaign.engagement_deadline = datetime.utcnow() + timedelta(days=7)
        
        db.session.add(campaign)
        db.session.commit()
        
        flash('Campaign created successfully.', 'success')
        return redirect(url_for('campaigns.manage'))
    
    return render_template('campaigns/create.html')

@campaigns.route('/<int:campaign_id>/engagement-report')
@login_required
def engagement_report(campaign_id):
    """View engagement report for a campaign"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
    
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Get engagement report
    report = get_campaign_engagement_report(campaign_id)
    
    return render_template('campaigns/engagement_report.html', campaign=campaign, report=report)

@campaigns.route('/<int:campaign_id>/track-engagement', methods=['POST'])
@login_required  
def track_engagement_manual(campaign_id):
    """Manually track engagement for a staff member"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    user_id = request.json.get('user_id')
    
    if not campaign.facebook_post_id:
        return jsonify({'success': False, 'message': 'No Facebook post linked to this campaign'})
    
    # Get user's Facebook token for engagement checking
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    facebook_token = user.decrypt_facebook_token()
    if not facebook_token:
        return jsonify({'success': False, 'message': 'User has no valid Facebook token'})
    
    # Track engagement
    success = track_campaign_engagement(user_id, campaign_id, campaign.facebook_post_id, facebook_token)
    
    if success:
        return jsonify({'success': True, 'message': 'Engagement tracked successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to track engagement'})

@campaigns.route('/<int:campaign_id>/bulk-check-engagement', methods=['POST'])
@login_required
def bulk_check_engagement(campaign_id):
    """Bulk check engagement for all staff on a campaign"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    
    if not campaign.facebook_post_id:
        return jsonify({'success': False, 'message': 'No Facebook post linked to this campaign'})
    
    # Run bulk engagement check
    stats = bulk_check_staff_engagement(campaign_id, campaign.facebook_post_id)
    
    return jsonify({
        'success': True, 
        'message': f'Checked engagement for {stats["checked"]} staff members',
        'stats': stats
    })

@campaigns.route('/<int:campaign_id>/send-reminders', methods=['POST'])
@login_required
def send_engagement_reminders_route(campaign_id):
    """Send engagement reminders to non-engaged staff"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    
    if not campaign.facebook_post_id:
        return jsonify({'success': False, 'message': 'No Facebook post linked to this campaign'})
    
    # Send reminders
    reminder_stats = send_engagement_reminders(campaign_id, campaign.facebook_post_id)
    
    return jsonify({
        'success': True,
        'message': f'Sent {reminder_stats["reminders_sent"]} reminders',
        'stats': reminder_stats
    })

@campaigns.route('/<int:campaign_id>/override-engagement', methods=['POST'])
@login_required
def override_engagement(campaign_id):
    """Manual override for engagement when Facebook API fails"""
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    user_id = request.json.get('user_id')
    liked = request.json.get('liked', False)
    shared = request.json.get('shared', False)
    
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID required'})
    
    # Check if engagement record exists
    existing_engagement = FacebookEngagement.query.filter_by(
        user_id=user_id,
        campaign_id=campaign_id,
        facebook_post_id=campaign.facebook_post_id
    ).first()
    
    if existing_engagement:
        # Update existing record
        existing_engagement.liked = liked
        existing_engagement.shared = shared
        existing_engagement.last_checked = datetime.utcnow()
        existing_engagement.verified = False  # Mark as manual override
    else:
        # Create new engagement record
        new_engagement = FacebookEngagement()
        new_engagement.user_id = user_id
        new_engagement.campaign_id = campaign_id
        new_engagement.facebook_post_id = campaign.facebook_post_id or 'manual_override'
        new_engagement.liked = liked
        new_engagement.shared = shared
        new_engagement.last_checked = datetime.utcnow()
        new_engagement.verified = False  # Mark as manual override
        db.session.add(new_engagement)
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Engagement manually recorded'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})

# Approval routes for campaigns
@campaigns.route('/pending-approvals')
@login_required
def pending_approvals():
    """View campaigns pending approval - only for Director, Media & Publicity"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        flash('Access denied. Only Director, Media & Publicity can approve campaigns.', 'error')
        return redirect(url_for('campaigns.list_campaigns'))
    
    pending_campaigns = Campaign.query.filter_by(approval_status='pending').order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns/pending_approvals.html', campaigns=pending_campaigns)

@campaigns.route('/<int:campaign_id>/approve', methods=['POST'])
@login_required
def approve_campaign(campaign_id):
    """Approve a campaign"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    
    campaign.approval_status = 'approved'
    campaign.approved_by_id = current_user.id
    campaign.approved_at = datetime.utcnow()
    campaign.published = True  # Auto-publish when approved
    
    db.session.commit()
    
    flash(f'Campaign "{campaign.title}" has been approved and published.', 'success')
    return redirect(url_for('campaigns.pending_approvals'))

@campaigns.route('/<int:campaign_id>/reject', methods=['POST'])
@login_required
def reject_campaign(campaign_id):
    """Reject a campaign"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        return jsonify({'success': False, 'message': 'Access denied'})
    
    campaign = Campaign.query.get_or_404(campaign_id)
    rejection_reason = request.form.get('rejection_reason', '')
    
    campaign.approval_status = 'rejected'
    campaign.approved_by_id = current_user.id
    campaign.approved_at = datetime.utcnow()
    campaign.rejection_reason = rejection_reason
    campaign.published = False
    
    db.session.commit()
    
    flash(f'Campaign "{campaign.title}" has been rejected.', 'success')
    return redirect(url_for('campaigns.pending_approvals'))

# Search functionality for campaigns  
@campaigns.route('/search')
def search():
    """Search campaigns"""
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('campaigns.list_campaigns'))
    
    # Search in title and content for published campaigns only
    campaigns_found = Campaign.query.filter(
        db.or_(
            Campaign.title.ilike(f'%{query}%'),
            Campaign.content.ilike(f'%{query}%')
        )
    ).filter_by(published=True).order_by(Campaign.created_at.desc()).all()
    
    return render_template('campaigns/search_results.html', campaigns=campaigns_found, query=query)