"""
Cache utilities for performance optimization
"""
from flask import current_app
from functools import wraps
from datetime import datetime, timedelta
from models import *


def cached_query(timeout=300, key_prefix=''):
    """
    Decorator to cache database query results
    
    Args:
        timeout: Cache timeout in seconds (default 5 minutes)
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = current_app.cache
            
            # Generate cache key from function name and arguments
            cache_key = f"{key_prefix}{func.__name__}_{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


@cached_query(timeout=300, key_prefix='home_')
def get_featured_campaigns():
    """Get featured campaigns for home page"""
    return Campaign.query.filter_by(featured=True, published=True).limit(3).all()


@cached_query(timeout=300, key_prefix='home_')
def get_latest_news():
    """Get latest news for home page"""
    return Campaign.query.filter_by(published=True).order_by(Campaign.created_at.desc()).limit(5).all()


@cached_query(timeout=600, key_prefix='stats_')
def get_user_statistics():
    """Get basic user statistics with caching"""
    return {
        'total_users': User.query.count(),
        'total_members': User.query.filter_by(approval_status=ApprovalStatus.APPROVED).count(),
        'pending_approvals': User.query.filter_by(approval_status=ApprovalStatus.PENDING).count(),
        'new_members_this_month': User.query.filter(
            User.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    }


@cached_query(timeout=600, key_prefix='stats_')
def get_campaign_statistics():
    """Get campaign statistics with caching"""
    try:
        active_campaigns = Campaign.query.filter_by(published=True).count()
        total_campaigns = Campaign.query.count()
        return {
            'active_campaigns': active_campaigns,
            'total_campaigns': total_campaigns
        }
    except:
        return {
            'active_campaigns': 0,
            'total_campaigns': 0
        }


@cached_query(timeout=600, key_prefix='stats_')
def get_event_statistics():
    """Get event statistics with caching"""
    try:
        total_events = Event.query.count()
        upcoming_events = Event.query.filter(Event.event_date >= datetime.utcnow()).count()
        return {
            'total_events': total_events,
            'upcoming_events': upcoming_events
        }
    except:
        return {
            'total_events': 0,
            'upcoming_events': 0
        }


@cached_query(timeout=1800, key_prefix='roles_')  # 30 minutes for role stats
def get_role_statistics():
    """Get role distribution statistics with caching"""
    role_stats = {}
    for role in RoleType:
        count = User.query.filter_by(role_type=role, approval_status=ApprovalStatus.APPROVED).count()
        role_stats[role.value] = count
    return role_stats


@cached_query(timeout=1800, key_prefix='zones_')  # 30 minutes for zone data
def get_zone_statistics():
    """Get zone performance data with caching"""
    zones = Zone.query.all()
    zone_data = []
    for zone in zones:
        zone_users = User.query.filter_by(zone_id=zone.id, approval_status=ApprovalStatus.APPROVED).count()
        zone_lgas = LGA.query.filter_by(zone_id=zone.id).count()
        zone_data.append({
            'id': zone.id,
            'name': zone.name,
            'users': zone_users,
            'lgas': zone_lgas,
            'performance': min(100, (zone_users / 100) * 100) if zone_users else 0
        })
    return zone_data


@cached_query(timeout=86400, key_prefix='leadership_')  # 24 hours for leadership (changes rarely)
def get_leadership_data():
    """Get leadership data with optimized queries and caching"""
    # Single query to get all leaders by role types
    all_leaders = User.query.filter(
        User.role_type.in_([
            RoleType.ADMIN, RoleType.EXECUTIVE, RoleType.ZONAL_COORDINATOR, 
            RoleType.LGA_LEADER, RoleType.WARD_LEADER
        ]),
        User.approval_status == ApprovalStatus.APPROVED
    ).order_by(
        # Order by role priority first, then by name
        User.role_type.asc(),
        User.full_name.asc()
    ).all()
    
    # Organize leaders by role for display
    ordered_leaders = []
    
    # State Coordinator first
    state_coordinator = next(
        (user for user in all_leaders 
         if user.role_type == RoleType.ADMIN and user.role_title == 'State Coordinator'), 
        None
    )
    if state_coordinator:
        ordered_leaders.append(state_coordinator)
    
    # Executives (up to 19)
    executives = [user for user in all_leaders if user.role_type == RoleType.EXECUTIVE][:19]
    ordered_leaders.extend(executives)
    
    # Zonal Coordinators (up to 3)
    zonal_coordinators = [user for user in all_leaders if user.role_type == RoleType.ZONAL_COORDINATOR][:3]
    ordered_leaders.extend(zonal_coordinators)
    
    # LGA and Ward Leaders (daily rotation - 7 total)
    lga_ward_leaders = [user for user in all_leaders 
                       if user.role_type in [RoleType.LGA_LEADER, RoleType.WARD_LEADER]]
    
    # Use date-based seed for consistent daily rotation
    import random
    current_date = datetime.now().date()
    random.seed(int(current_date.strftime('%Y%m%d')))
    random.shuffle(lga_ward_leaders)
    daily_coordinators = lga_ward_leaders[:7]
    ordered_leaders.extend(daily_coordinators)
    
    return ordered_leaders


@cached_query(timeout=600, key_prefix='media_')
def get_media_gallery_data():
    """Get media gallery data with caching"""
    photos = Media.query.filter_by(file_type='photo', public=True).order_by(Media.created_at.desc()).all()
    videos = Media.query.filter_by(file_type='video', public=True).order_by(Media.created_at.desc()).all()
    return {'photos': photos, 'videos': videos}


def invalidate_cache_pattern(pattern):
    """
    Invalidate cache entries matching a pattern
    
    Args:
        pattern: Cache key pattern to invalidate (e.g., 'user_stats_*')
    """
    cache = current_app.cache
    if hasattr(cache.cache, 'delete_many'):
        # For Redis cache
        cache.cache.delete_many(pattern)
    else:
        # For simple cache, clear all (less efficient but works)
        cache.clear()


def invalidate_user_caches():
    """Invalidate all user-related caches when user data changes"""
    invalidate_cache_pattern('stats_*')
    invalidate_cache_pattern('roles_*')
    invalidate_cache_pattern('zones_*')
    invalidate_cache_pattern('leadership_*')


def invalidate_campaign_caches():
    """Invalidate campaign-related caches when campaign data changes"""
    invalidate_cache_pattern('home_*')
    invalidate_cache_pattern('stats_*')


def invalidate_media_caches():
    """Invalidate media-related caches when media data changes"""
    invalidate_cache_pattern('media_*')