"""
Member Activity Tracking System for KPN
Comprehensive tracking of member activities from Facebook engagement to duties
"""

from extensions import db
from models import User, ActivityLog, FacebookEngagement, MemberStats, DutyLog
from datetime import datetime, timedelta
import logging

# Activity point values
ACTIVITY_POINTS = {
    'facebook_follow': 10,
    'facebook_like': 2,
    'facebook_comment': 5,
    'facebook_share': 8,
    'duty_completed': 15,
    'duty_overdue': -5,
    'event_attended': 12,
    'campaign_participated': 10,
    'media_uploaded': 8,
    'profile_updated': 3,
    'disciplinary_warning': -10,
    'disciplinary_suspension': -25,
    'role_promotion': 20
}

def log_activity(user_id, activity_type, description, points=None, **kwargs):
    """
    Log any member activity and automatically update statistics
    
    Args:
        user_id: ID of the user performing the activity
        activity_type: Type of activity (e.g., 'facebook_like', 'duty_completed')
        description: Human-readable description of the activity
        points: Override default points for this activity
        **kwargs: Additional fields (campaign_id, event_id, media_id, duty_log_id)
    """
    try:
        # Calculate points
        if points is None:
            points = ACTIVITY_POINTS.get(activity_type, 0)
        
        # Create activity log entry
        activity = ActivityLog(
            user_id=user_id,
            activity_type=activity_type,
            activity_description=description,
            points_earned=points,
            campaign_id=kwargs.get('campaign_id'),
            event_id=kwargs.get('event_id'),
            media_id=kwargs.get('media_id'),
            duty_log_id=kwargs.get('duty_log_id')
        )
        
        db.session.add(activity)
        
        # Update member statistics (will commit within the function)
        db.session.flush()  # Ensure activity log is flushed first
        update_member_stats(user_id)
        
        db.session.commit()
        
        logging.info(f"Activity logged for user {user_id}: {activity_type} - {description}")
        return True
        
    except Exception as e:
        logging.error(f"Error logging activity for user {user_id}: {str(e)}")
        db.session.rollback()
        return False

def track_facebook_engagement(user_id, engagement_type, post_id=None, post_url=None):
    """
    Track Facebook engagement activities
    
    Args:
        user_id: ID of the user
        engagement_type: Type of engagement (like, comment, share, react)
        post_id: Facebook post ID (if available)
        post_url: URL of the Facebook post
    """
    try:
        # Create Facebook engagement record
        engagement = FacebookEngagement(
            user_id=user_id,
            engagement_type=engagement_type,
            post_id=post_id,
            post_url=post_url,
            verified=False  # Will be verified later via API if needed
        )
        
        db.session.add(engagement)
        
        # Log as general activity
        description = f"Facebook {engagement_type}"
        if post_url:
            description += f" on post: {post_url}"
            
        log_activity(
            user_id=user_id,
            activity_type=f'facebook_{engagement_type}',
            description=description
        )
        
        return True
        
    except Exception as e:
        logging.error(f"Error tracking Facebook engagement for user {user_id}: {str(e)}")
        db.session.rollback()
        return False

def update_member_stats(user_id):
    """
    Update or create member statistics for a user
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return False
        
        # Get or create member stats
        stats = MemberStats.query.filter_by(user_id=user_id).first()
        if not stats:
            stats = MemberStats(user_id=user_id)
            db.session.add(stats)
        
        # Calculate statistics
        stats.total_points = db.session.query(db.func.sum(ActivityLog.points_earned))\
            .filter_by(user_id=user_id).scalar() or 0
        
        stats.duties_completed = DutyLog.query.filter_by(
            user_id=user_id, completion_status='completed'
        ).count()
        
        stats.duties_overdue = DutyLog.query.filter_by(
            user_id=user_id, completion_status='overdue'
        ).count()
        
        stats.facebook_engagements = FacebookEngagement.query.filter_by(
            user_id=user_id
        ).count()
        
        stats.events_attended = ActivityLog.query.filter_by(
            user_id=user_id, activity_type='event_attended'
        ).count()
        
        stats.campaigns_participated = ActivityLog.query.filter_by(
            user_id=user_id, activity_type='campaign_participated'
        ).count()
        
        # Get last activity date
        last_activity = ActivityLog.query.filter_by(user_id=user_id)\
            .order_by(ActivityLog.created_at.desc()).first()
        stats.last_activity_date = last_activity.created_at if last_activity else None
        
        # Calculate activity score (0-100)
        stats.activity_score = calculate_activity_score(stats)
        stats.updated_at = datetime.utcnow()
        
        # Commit the changes
        db.session.commit()
        return True
        
    except Exception as e:
        logging.error(f"Error updating member stats for user {user_id}: {str(e)}")
        return False

def calculate_activity_score(stats):
    """
    Calculate a comprehensive activity score (0-100) based on member statistics
    """
    try:
        score = 0.0
        
        # Base score from points (max 40 points)
        if stats.total_points > 0:
            score += min(stats.total_points / 5, 40)
        
        # Duty completion rate (max 30 points)
        total_duties = stats.duties_completed + stats.duties_overdue
        if total_duties > 0:
            completion_rate = stats.duties_completed / total_duties
            score += completion_rate * 30
        
        # Facebook engagement (max 15 points)
        score += min(stats.facebook_engagements, 15)
        
        # Event participation (max 10 points)
        score += min(stats.events_attended, 10)
        
        # Campaign participation (max 5 points)
        score += min(stats.campaigns_participated, 5)
        
        # Recent activity bonus/penalty
        if stats.last_activity_date:
            days_since_activity = (datetime.utcnow() - stats.last_activity_date).days
            if days_since_activity <= 7:
                score += 5  # Recent activity bonus
            elif days_since_activity > 30:
                score -= 10  # Inactivity penalty
        
        return max(0.0, min(100.0, score))
        
    except:
        return 0.0

def get_member_activity_summary(user_id, days=30):
    """
    Get a comprehensive activity summary for a member
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return None
        
        # Get date range
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get recent activities
        recent_activities = ActivityLog.query.filter(
            ActivityLog.user_id == user_id,
            ActivityLog.created_at >= start_date
        ).order_by(ActivityLog.created_at.desc()).all()
        
        # Get member stats
        stats = user.member_stats
        if not stats:
            update_member_stats(user_id)
            stats = user.member_stats
        
        # Activity breakdown
        activity_breakdown = {}
        for activity in recent_activities:
            activity_type = activity.activity_type
            if activity_type in activity_breakdown:
                activity_breakdown[activity_type] += 1
            else:
                activity_breakdown[activity_type] = 1
        
        return {
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'role_type': user.role_type.value,
                'role_title': user.role_title
            },
            'stats': {
                'total_points': stats.total_points if stats else 0,
                'activity_score': stats.activity_score if stats else 0.0,
                'duties_completed': stats.duties_completed if stats else 0,
                'duties_overdue': stats.duties_overdue if stats else 0,
                'facebook_engagements': stats.facebook_engagements if stats else 0,
                'events_attended': stats.events_attended if stats else 0,
                'campaigns_participated': stats.campaigns_participated if stats else 0,
                'last_activity_date': stats.last_activity_date if stats else None
            },
            'recent_activities': [{
                'type': activity.activity_type,
                'description': activity.activity_description,
                'points': activity.points_earned,
                'date': activity.created_at
            } for activity in recent_activities],
            'activity_breakdown': activity_breakdown,
            'period_days': days
        }
        
    except Exception as e:
        logging.error(f"Error getting activity summary for user {user_id}: {str(e)}")
        return None

def get_top_performers(limit=10, days=30):
    """
    Get top performing members based on activity score
    """
    try:
        # Get date range
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get top performers
        top_performers = db.session.query(MemberStats, User)\
            .join(User, MemberStats.user_id == User.id)\
            .filter(User.approval_status == 'approved')\
            .order_by(MemberStats.activity_score.desc())\
            .limit(limit)\
            .all()
        
        results = []
        for stats, user in top_performers:
            # Get recent activity count
            recent_activity_count = ActivityLog.query.filter(
                ActivityLog.user_id == user.id,
                ActivityLog.created_at >= start_date
            ).count()
            
            results.append({
                'user': {
                    'id': user.id,
                    'full_name': user.full_name,
                    'role_type': user.role_type.value,
                    'role_title': user.role_title,
                    'zone': user.zone.name if user.zone else None,
                    'lga': user.lga.name if user.lga else None
                },
                'stats': {
                    'activity_score': stats.activity_score,
                    'total_points': stats.total_points,
                    'recent_activities': recent_activity_count
                }
            })
        
        return results
        
    except Exception as e:
        logging.error(f"Error getting top performers: {str(e)}")
        return []

def auto_track_duty_completion(duty_log_id):
    """
    Automatically track when a duty is completed
    """
    try:
        duty = DutyLog.query.get(duty_log_id)
        if duty and duty.completion_status == 'completed':
            log_activity(
                user_id=duty.user_id,
                activity_type='duty_completed',
                description=f"Completed duty: {duty.duty_description[:50]}...",
                duty_log_id=duty_log_id
            )
            return True
        return False
    except Exception as e:
        logging.error(f"Error auto-tracking duty completion: {str(e)}")
        return False

def auto_track_facebook_follow(user_id):
    """
    Automatically track when a user follows the Facebook page
    """
    try:
        log_activity(
            user_id=user_id,
            activity_type='facebook_follow',
            description="Followed KPN official Facebook page"
        )
        return True
    except Exception as e:
        logging.error(f"Error auto-tracking Facebook follow: {str(e)}")
        return False

def auto_track_duty_completion(duty_log_id):
    """
    Automatically track when a duty is completed
    """
    try:
        duty = DutyLog.query.get(duty_log_id)
        if duty and duty.completion_status == 'completed':
            log_activity(
                user_id=duty.user_id,
                activity_type='duty_completed',
                description=f"Completed duty: {duty.duty_description[:50]}...",
                duty_log_id=duty_log_id
            )
            return True
        return False
    except Exception as e:
        logging.error(f"Error auto-tracking duty completion: {str(e)}")
        return False