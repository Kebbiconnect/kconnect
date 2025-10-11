from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import *
import random
from datetime import datetime

core = Blueprint('core', __name__)

@core.route('/')
def home():
    # Get latest campaigns and news with caching
    from utils.cache_utils import get_featured_campaigns, get_latest_news
    featured_campaigns = get_featured_campaigns()
    latest_news = get_latest_news()
    return render_template('core/home.html', campaigns=featured_campaigns, news=latest_news)

@core.route('/about')
def about():
    return render_template('core/about.html')

@core.route('/leadership')
def leadership():
    # Use optimized cached leadership data
    from utils.cache_utils import get_leadership_data
    ordered_leaders = get_leadership_data()
    
    # For filtering (keep existing filter functionality)
    zone_filter = request.args.get('zone')
    lga_filter = request.args.get('lga')
    ward_filter = request.args.get('ward')
    
    # If filters are applied, modify the display accordingly
    if zone_filter or lga_filter or ward_filter:
        filtered_query = User.query.filter(
            User.role_type.in_([RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER]),
            User.approval_status == ApprovalStatus.APPROVED
        )
        
        if zone_filter:
            filtered_query = filtered_query.filter_by(zone_id=zone_filter)
        if lga_filter:
            filtered_query = filtered_query.filter_by(lga_id=lga_filter)
        if ward_filter:
            filtered_query = filtered_query.filter_by(ward_id=ward_filter)
        
        filtered_leaders = filtered_query.all()
        # Keep state coordinator and executives, but replace others with filtered results
        ordered_leaders = [l for l in ordered_leaders if l.role_type in [RoleType.ADMIN, RoleType.EXECUTIVE]] + filtered_leaders
    
    zones = Zone.query.all()
    lgas = LGA.query.all()
    wards = Ward.query.all()
    
    # Extract executives from ordered leaders for template context
    executives = [leader for leader in ordered_leaders if leader.role_type == RoleType.EXECUTIVE]
    
    return render_template('core/leadership.html', 
                         executives=executives, 
                         leaders=ordered_leaders, 
                         zones=zones, 
                         lgas=lgas, 
                         wards=wards)

@core.route('/join')
def join():
    zones = Zone.query.all()
    return render_template('core/join.html', zones=zones)

@core.route('/media')
def media_gallery():
    photos = Media.query.filter_by(file_type='photo', public=True).order_by(Media.created_at.desc()).all()
    videos = Media.query.filter_by(file_type='video', public=True).order_by(Media.created_at.desc()).all()
    return render_template('core/media.html', photos=photos, videos=videos)

@core.route('/news')
def news():
    campaigns = Campaign.query.filter_by(published=True).order_by(Campaign.created_at.desc()).all()
    return render_template('core/news.html', campaigns=campaigns)

@core.route('/contact')
def contact():
    return render_template('core/contact.html')

@core.route('/support')
def support():
    donations = Donation.query.filter_by(active=True).all()
    return render_template('core/support.html', donations=donations)

@core.route('/faq')
def faq():
    return render_template('core/faq.html')

@core.route('/code-of-conduct')
def code_of_conduct():
    return render_template('core/code_of_conduct.html')