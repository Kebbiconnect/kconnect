"""
Facebook API utility functions for KPN system
Handles engagement tracking, page following verification, and post interactions
"""

import os
import requests
from datetime import datetime, timedelta
from flask import current_app
from models import db, User, FacebookEngagement, Campaign, ApprovalStatus, RoleType, StaffStatus
from typing import Dict, List, Optional, Tuple

# Facebook API Configuration
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID')
FACEBOOK_API_VERSION = 'v18.0'
FACEBOOK_GRAPH_URL = f'https://graph.facebook.com/{FACEBOOK_API_VERSION}'


class FacebookAPIError(Exception):
    """Custom exception for Facebook API errors"""
    pass


def get_app_access_token() -> Optional[str]:
    """
    Get app access token for Facebook API calls
    Returns: App access token string or None if failed
    """
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        current_app.logger.warning("Facebook credentials not configured")
        return None
    
    try:
        url = f"{FACEBOOK_GRAPH_URL}/oauth/access_token"
        params = {
            'client_id': FACEBOOK_APP_ID,
            'client_secret': FACEBOOK_APP_SECRET,
            'grant_type': 'client_credentials'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        return data.get('access_token')
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Failed to get Facebook app access token: {e}")
        return None


def verify_user_token(user_token: str, facebook_user_id: str) -> bool:
    """
    Verify that a user access token is valid and belongs to the specified user
    
    Args:
        user_token: Facebook user access token
        facebook_user_id: Facebook user ID to verify against
        
    Returns: True if token is valid and belongs to user, False otherwise
    """
    try:
        url = f"{FACEBOOK_GRAPH_URL}/me"
        params = {
            'access_token': user_token,
            'fields': 'id'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        return data.get('id') == facebook_user_id
        
    except requests.exceptions.RequestException:
        return False


def check_page_engagement(facebook_user_id: str, post_id: str, user_token: str) -> Dict[str, bool]:
    """
    Check if a user has engaged with a specific Facebook post (liked or shared)
    
    Args:
        facebook_user_id: Facebook ID of the user
        post_id: Facebook post ID to check engagement
        user_token: User's Facebook access token
        
    Returns: Dictionary with 'liked' and 'shared' boolean values
    """
    engagement = {'liked': False, 'shared': False}
    
    if not verify_user_token(user_token, facebook_user_id):
        current_app.logger.warning(f"Invalid token for user {facebook_user_id}")
        return engagement
    
    try:
        # Check if user liked the post
        like_url = f"{FACEBOOK_GRAPH_URL}/{post_id}/likes"
        like_params = {
            'access_token': user_token,
            'limit': 1000  # Adjust based on expected engagement
        }
        
        like_response = requests.get(like_url, params=like_params, timeout=10)
        if like_response.status_code == 200:
            like_data = like_response.json()
            if 'data' in like_data:
                for like in like_data['data']:
                    if like.get('id') == facebook_user_id:
                        engagement['liked'] = True
                        break
        
        # Check if user shared the post (this requires additional permissions)
        # Note: Facebook has limited access to share data due to privacy policies
        # This is a simplified check that may not capture all shares
        share_url = f"{FACEBOOK_GRAPH_URL}/{post_id}/sharedposts"
        share_params = {
            'access_token': user_token,
            'limit': 100
        }
        
        share_response = requests.get(share_url, params=share_params, timeout=10)
        if share_response.status_code == 200:
            share_data = share_response.json()
            if 'data' in share_data:
                for share in share_data['data']:
                    if share.get('from', {}).get('id') == facebook_user_id:
                        engagement['shared'] = True
                        break
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error checking post engagement: {e}")
    
    return engagement


def track_campaign_engagement(user_id: int, campaign_id: int, facebook_post_id: str, user_token: str) -> bool:
    """
    Track and record user engagement with a campaign Facebook post
    
    Args:
        user_id: KPN user ID
        campaign_id: Campaign ID
        facebook_post_id: Facebook post ID for the campaign
        user_token: User's Facebook access token
        
    Returns: True if engagement was successfully tracked, False otherwise
    """
    try:
        user = User.query.get(user_id)
        if not user or not user.facebook_user_id:
            current_app.logger.warning(f"User {user_id} not found or no Facebook ID")
            return False
        
        # Check engagement
        engagement = check_page_engagement(user.facebook_user_id, facebook_post_id, user_token)
        
        # Check if engagement record already exists
        existing_engagement = FacebookEngagement.query.filter_by(
            user_id=user_id,
            campaign_id=campaign_id,
            facebook_post_id=facebook_post_id
        ).first()
        
        if existing_engagement:
            # Update existing record
            existing_engagement.liked = engagement['liked']
            existing_engagement.shared = engagement['shared']
            existing_engagement.last_checked = datetime.utcnow()
        else:
            # Create new engagement record
            new_engagement = FacebookEngagement()
            new_engagement.user_id = user_id
            new_engagement.campaign_id = campaign_id
            new_engagement.facebook_post_id = facebook_post_id
            new_engagement.liked = engagement['liked']
            new_engagement.shared = engagement['shared']
            new_engagement.last_checked = datetime.utcnow()
            db.session.add(new_engagement)
        
        # Update user engagement status after tracking
        user.update_engagement_status()
        user.update_activity_date()
        user.update_staff_status()
        
        db.session.commit()
        
        current_app.logger.info(
            f"Tracked engagement for user {user_id} on post {facebook_post_id}: "
            f"liked={engagement['liked']}, shared={engagement['shared']}"
        )
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error tracking campaign engagement: {e}")
        db.session.rollback()
        return False


def bulk_check_staff_engagement(campaign_id: int, facebook_post_id: str) -> Dict[str, int]:
    """
    Check engagement for all staff members on a specific campaign post
    
    Args:
        campaign_id: Campaign ID
        facebook_post_id: Facebook post ID for the campaign
        
    Returns: Dictionary with engagement statistics
    """
    stats = {
        'total_staff': 0,
        'checked': 0,
        'liked': 0,
        'shared': 0,
        'engaged': 0,  # liked OR shared
        'errors': 0
    }
    
    try:
        # Get all approved staff members with Facebook verification
        staff_members = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.facebook_verified == True,
            User.facebook_user_id.isnot(None),
            User.role_type != RoleType.GENERAL_MEMBER
        ).all()
        
        stats['total_staff'] = len(staff_members)
        
        for user in staff_members:
            try:
                # For bulk checking, we'll use a simplified approach
                # In a real scenario, you'd need each user's current access token
                # This is a limitation of Facebook's API - user tokens expire
                
                # Check existing engagement record
                engagement_record = FacebookEngagement.query.filter_by(
                    user_id=user.id,
                    campaign_id=campaign_id,
                    facebook_post_id=facebook_post_id
                ).first()
                
                if engagement_record:
                    stats['checked'] += 1
                    if engagement_record.liked:
                        stats['liked'] += 1
                    if engagement_record.shared:
                        stats['shared'] += 1
                    if engagement_record.liked or engagement_record.shared:
                        stats['engaged'] += 1
                    
                    # Auto-update user engagement and staff status
                    user.update_engagement_status()
                    user.update_activity_date()
                    user.update_staff_status()
                
            except Exception as e:
                stats['errors'] += 1
                current_app.logger.error(f"Error checking engagement for user {user.id}: {e}")
        
    except Exception as e:
        current_app.logger.error(f"Error in bulk engagement check: {e}")
    
    # Commit all status updates
    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error committing bulk engagement updates: {e}")
        db.session.rollback()
    
    return stats


def get_user_engagement_summary(user_id: int, days: int = 30) -> Dict[str, any]:
    """
    Get engagement summary for a user over the specified period
    
    Args:
        user_id: KPN user ID
        days: Number of days to look back (default 30)
        
    Returns: Dictionary with engagement summary
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        engagements = FacebookEngagement.query.filter(
            FacebookEngagement.user_id == user_id,
            FacebookEngagement.last_checked >= start_date
        ).all()
        
        summary = {
            'total_posts': len(engagements),
            'liked_posts': sum(1 for e in engagements if e.liked),
            'shared_posts': sum(1 for e in engagements if e.shared),
            'engagement_rate': 0,
            'last_activity': None
        }
        
        if engagements:
            engaged_posts = sum(1 for e in engagements if e.liked or e.shared)
            summary['engagement_rate'] = (engaged_posts / len(engagements)) * 100
            summary['last_activity'] = max(e.last_checked for e in engagements)
        
        return summary
        
    except Exception as e:
        current_app.logger.error(f"Error getting engagement summary for user {user_id}: {e}")
        return {
            'total_posts': 0,
            'liked_posts': 0,
            'shared_posts': 0,
            'engagement_rate': 0,
            'last_activity': None
        }


def auto_update_all_staff_engagement_status() -> Dict[str, int]:
    """
    Automatically update engagement status for all staff members
    This function should be called periodically (e.g., daily) to keep status current
    
    Returns: Dictionary with update statistics
    """
    stats = {
        'total_staff': 0,
        'updated': 0,
        'active': 0,
        'irregular': 0,
        'inactive': 0,
        'errors': 0
    }
    
    try:
        # Get all approved staff members
        staff_members = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER
        ).all()
        
        stats['total_staff'] = len(staff_members)
        
        for user in staff_members:
            try:
                # Update engagement status
                user.update_engagement_status()
                user.update_staff_status()
                
                # Track status distribution
                if user.staff_status == StaffStatus.ACTIVE:
                    stats['active'] += 1
                elif user.staff_status == StaffStatus.IRREGULAR:
                    stats['irregular'] += 1
                elif user.staff_status == StaffStatus.INACTIVE:
                    stats['inactive'] += 1
                
                stats['updated'] += 1
                
            except Exception as e:
                stats['errors'] += 1
                current_app.logger.error(f"Error updating status for user {user.id}: {e}")
        
        # Commit all updates
        db.session.commit()
        
        current_app.logger.info(
            f"Auto-updated engagement status for {stats['updated']} staff members. "
            f"Active: {stats['active']}, Irregular: {stats['irregular']}, Inactive: {stats['inactive']}"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in auto engagement status update: {e}")
        db.session.rollback()
        stats['errors'] += 1
    
    return stats


def enhanced_manual_override_engagement(user_id: int, campaign_id: int, 
                                       facebook_post_id: str, liked: bool = False, 
                                       shared: bool = False, commented: bool = False,
                                       override_reason: str = "Manual override by supervisor") -> bool:
    """
    Enhanced manual override for engagement with detailed tracking
    
    Args:
        user_id: KPN user ID
        campaign_id: Campaign ID
        facebook_post_id: Facebook post ID
        liked: Whether user liked the post
        shared: Whether user shared the post
        commented: Whether user commented on the post
        override_reason: Reason for manual override
        
    Returns: True if override was successful, False otherwise
    """
    try:
        user = User.query.get(user_id)
        if not user:
            current_app.logger.warning(f"User {user_id} not found for engagement override")
            return False
        
        # Check if engagement record exists
        existing_engagement = FacebookEngagement.query.filter_by(
            user_id=user_id,
            campaign_id=campaign_id,
            facebook_post_id=facebook_post_id
        ).first()
        
        if existing_engagement:
            # Update existing record
            existing_engagement.liked = liked
            existing_engagement.shared = shared
            existing_engagement.commented = commented
            existing_engagement.last_checked = datetime.utcnow()
            existing_engagement.verified = True  # Manual overrides count as verified for status updates
        else:
            # Create new engagement record
            new_engagement = FacebookEngagement(
                user_id=user_id,
                campaign_id=campaign_id,
                facebook_post_id=facebook_post_id,
                liked=liked,
                shared=shared,
                commented=commented,
                last_checked=datetime.utcnow(),
                verified=True  # Manual overrides count as verified for status updates
            )
            db.session.add(new_engagement)
        
        # Update user status
        user.update_engagement_status()
        user.update_activity_date()
        user.update_staff_status()
        
        db.session.commit()
        
        current_app.logger.info(
            f"Manual engagement override for user {user_id} on post {facebook_post_id}. "
            f"Liked: {liked}, Shared: {shared}, Commented: {commented}. Reason: {override_reason}"
        )
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error in enhanced manual engagement override: {e}")
        db.session.rollback()
        return False


def verify_facebook_page_follow_api(facebook_user_id: str, access_token: str) -> bool:
    """
    Enhanced version of Facebook page follow verification using Graph API
    
    Args:
        facebook_user_id: Facebook user ID
        access_token: User's Facebook access token
        
    Returns: True if user follows the KPN page, False otherwise
    """
    if not FACEBOOK_PAGE_ID or not facebook_user_id or not access_token:
        return False
    
    if not verify_user_token(access_token, facebook_user_id):
        return False
    
    try:
        # Check if user likes the page
        url = f"{FACEBOOK_GRAPH_URL}/{FACEBOOK_PAGE_ID}/likes"
        params = {
            'access_token': access_token,
            'fields': 'id,name',
            'limit': 100
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if 'data' in data:
            for like in data['data']:
                if like.get('id') == facebook_user_id:
                    return True
        
        return False
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error verifying page follow: {e}")
        return False


def get_campaign_engagement_report(campaign_id: int) -> Dict[str, any]:
    """
    Generate comprehensive engagement report for a campaign
    
    Args:
        campaign_id: Campaign ID
        
    Returns: Dictionary with detailed engagement report
    """
    try:
        campaign = Campaign.query.get(campaign_id)
        if not campaign:
            return {'error': 'Campaign not found'}
        
        engagements = FacebookEngagement.query.filter_by(campaign_id=campaign_id).all()
        
        report = {
            'campaign_title': campaign.title,
            'campaign_id': campaign_id,
            'total_interactions': len(engagements),
            'likes': sum(1 for e in engagements if e.liked),
            'shares': sum(1 for e in engagements if e.shared),
            'engagement_by_role': {},
            'non_engaged_staff': [],
            'engagement_rate': 0
        }
        
        # Get engagement by role
        for engagement in engagements:
            user = User.query.get(engagement.user_id)
            if user:
                role = user.role_type.value
                if role not in report['engagement_by_role']:
                    report['engagement_by_role'][role] = {
                        'total': 0, 'liked': 0, 'shared': 0, 'engaged': 0
                    }
                
                report['engagement_by_role'][role]['total'] += 1
                if engagement.liked:
                    report['engagement_by_role'][role]['liked'] += 1
                if engagement.shared:
                    report['engagement_by_role'][role]['shared'] += 1
                if engagement.liked or engagement.shared:
                    report['engagement_by_role'][role]['engaged'] += 1
        
        # Find non-engaged staff
        engaged_user_ids = {e.user_id for e in engagements if e.liked or e.shared}
        all_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.facebook_verified == True
        ).all()
        
        for user in all_staff:
            if user.id not in engaged_user_ids:
                report['non_engaged_staff'].append({
                    'id': user.id,
                    'name': user.full_name,
                    'role': user.role_type.value,
                    'location': user.get_location_hierarchy()
                })
        
        # Calculate overall engagement rate
        total_staff = len(all_staff)
        if total_staff > 0:
            engaged_staff = len(engaged_user_ids)
            report['engagement_rate'] = (engaged_staff / total_staff) * 100
        
        return report
        
    except Exception as e:
        current_app.logger.error(f"Error generating engagement report: {e}")
        return {'error': f'Failed to generate report: {str(e)}'}


def send_engagement_reminders(campaign_id: int, facebook_post_id: str) -> Dict[str, int]:
    """
    Send reminders to staff who haven't engaged with a campaign post
    
    Args:
        campaign_id: Campaign ID
        facebook_post_id: Facebook post ID
        
    Returns: Dictionary with reminder statistics
    """
    try:
        # Get non-engaged staff
        engaged_user_ids = set()
        engagements = FacebookEngagement.query.filter_by(
            campaign_id=campaign_id,
            facebook_post_id=facebook_post_id
        ).all()
        
        for engagement in engagements:
            if engagement.liked or engagement.shared:
                engaged_user_ids.add(engagement.user_id)
        
        # Get all staff who should engage
        all_staff = User.query.filter(
            User.approval_status == ApprovalStatus.APPROVED,
            User.role_type != RoleType.GENERAL_MEMBER,
            User.facebook_verified == True
        ).all()
        
        reminders_sent = 0
        errors = 0
        
        for user in all_staff:
            if user.id not in engaged_user_ids:
                try:
                    # Here you would integrate with your email service
                    # For now, we'll just log the reminder
                    current_app.logger.info(
                        f"Engagement reminder needed for user {user.id} ({user.full_name}) "
                        f"for campaign {campaign_id}"
                    )
                    reminders_sent += 1
                    
                except Exception as e:
                    current_app.logger.error(f"Error sending reminder to user {user.id}: {e}")
                    errors += 1
        
        return {
            'reminders_sent': reminders_sent,
            'errors': errors,
            'total_non_engaged': len(all_staff) - len(engaged_user_ids)
        }
        
    except Exception as e:
        current_app.logger.error(f"Error sending engagement reminders: {e}")
        return {'reminders_sent': 0, 'errors': 1, 'total_non_engaged': 0}