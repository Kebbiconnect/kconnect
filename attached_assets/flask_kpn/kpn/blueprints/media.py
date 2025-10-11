from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import *
from werkzeug.utils import secure_filename
from datetime import datetime
import os

media = Blueprint('media', __name__)

@media.route('/')
def gallery():
    # Use cached media gallery data for better performance
    from utils.cache_utils import get_media_gallery_data
    media_data = get_media_gallery_data()
    return render_template('media/gallery.html', photos=media_data['photos'], videos=media_data['videos'])

@media.route('/manage')
@login_required
def manage():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    media_files = Media.query.order_by(Media.created_at.desc()).all()
    return render_template('media/manage.html', media_files=media_files)

@media.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # Allow ADMIN, EXECUTIVE, and Publicity Officers to upload media
    allowed_roles = [RoleType.ADMIN, RoleType.EXECUTIVE]
    allowed_publicity_roles = ['Publicity', 'Assistant Director of Media & Publicity', 'Director of Media & Publicity']
    
    if current_user.role_type not in allowed_roles:
        if not (current_user.role_type in [RoleType.ZONAL_COORDINATOR, RoleType.LGA_LEADER, RoleType.WARD_LEADER, RoleType.EXECUTIVE] and 
                current_user.role_title in allowed_publicity_roles):
            flash('Access denied.', 'error')
            return redirect(url_for('core.home'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        file_type = request.form['file_type']
        public = request.form.get('public') == 'on'
        
        # Handle file upload
        uploaded_file = request.files.get('media_file')
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.filename}")
            
            # Create upload directory
            upload_dir = f"static/uploads/{file_type}s"
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(upload_dir, filename)
            uploaded_file.save(file_path)
            
            # Publicity officers cannot directly make media public - needs approval
            can_publish_directly = current_user.role_type in [RoleType.ADMIN] or \
                                  (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity')
            
            # Create media record
            media_item = Media(
                title=title,
                description=description,
                file_path=f"uploads/{file_type}s/{filename}",
                file_type=file_type,
                uploaded_by_id=current_user.id,
                public=False,  # Always False initially - requires approval
                approval_status='approved' if can_publish_directly else 'pending'
            )
            
            # Auto-approve and make public if user has direct publishing rights
            if can_publish_directly:
                media_item.public = public
                media_item.approved_by_id = current_user.id
                media_item.approved_at = datetime.utcnow()
            
            db.session.add(media_item)
            db.session.commit()
            
            flash('Media uploaded successfully.', 'success')
            return redirect(url_for('media.manage'))
        else:
            flash('Please select a file to upload.', 'error')
    
    return render_template('media/upload.html')

# Approval routes for media
@media.route('/pending-approvals')
@login_required
def pending_approvals():
    """View media pending approval - only for Director, Media & Publicity"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        flash('Access denied. Only Director, Media & Publicity can approve media.', 'error')
        return redirect(url_for('media.gallery'))
    
    pending_media = Media.query.filter_by(approval_status='pending').order_by(Media.created_at.desc()).all()
    return render_template('media/pending_approvals.html', media_files=pending_media)

@media.route('/<int:media_id>/approve', methods=['POST'])
@login_required
def approve_media(media_id):
    """Approve a media item"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        return jsonify({'success': False, 'message': 'Access denied'})
    
    media_item = Media.query.get_or_404(media_id)
    
    media_item.approval_status = 'approved'
    media_item.approved_by_id = current_user.id
    media_item.approved_at = datetime.utcnow()
    media_item.public = True  # Auto-publish when approved
    
    db.session.commit()
    
    flash(f'Media "{media_item.title}" has been approved and published.', 'success')
    return redirect(url_for('media.pending_approvals'))

@media.route('/<int:media_id>/reject', methods=['POST'])
@login_required
def reject_media(media_id):
    """Reject a media item"""
    if not (current_user.role_type == RoleType.EXECUTIVE and current_user.role_title == 'Director of Media & Publicity'):
        return jsonify({'success': False, 'message': 'Access denied'})
    
    media_item = Media.query.get_or_404(media_id)
    rejection_reason = request.form.get('rejection_reason', '')
    
    media_item.approval_status = 'rejected'
    media_item.approved_by_id = current_user.id
    media_item.approved_at = datetime.utcnow()
    media_item.rejection_reason = rejection_reason
    media_item.public = False
    
    db.session.commit()
    
    flash(f'Media "{media_item.title}" has been rejected.', 'success')
    return redirect(url_for('media.pending_approvals'))

# Search functionality
@media.route('/search')
@login_required  
def search():
    """Search media files"""
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('media.gallery'))
    
    # Search in title and description
    media_files = Media.query.filter(
        db.or_(
            Media.title.ilike(f'%{query}%'),
            Media.description.ilike(f'%{query}%')
        )
    ).filter_by(public=True).order_by(Media.created_at.desc()).all()
    
    return render_template('media/search_results.html', media_files=media_files, query=query)