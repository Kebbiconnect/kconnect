from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import *

donations = Blueprint('donations', __name__)

@donations.route('/')
def list_donations():
    donations = Donation.query.filter_by(active=True).all()
    return render_template('donations/list.html', donations=donations)

@donations.route('/manage')
@login_required
def manage():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    donations = Donation.query.all()
    return render_template('donations/manage.html', donations=donations)

@donations.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if current_user.role_type not in [RoleType.ADMIN, RoleType.EXECUTIVE]:
        flash('Access denied.', 'error')
        return redirect(url_for('core.home'))
    
    if request.method == 'POST':
        donation = Donation(
            bank_name=request.form['bank_name'],
            account_name=request.form['account_name'],
            account_number=request.form['account_number'],
            description=request.form.get('description', ''),
            active=request.form.get('active') == 'on'
        )
        
        db.session.add(donation)
        db.session.commit()
        
        flash('Bank details added successfully.', 'success')
        return redirect(url_for('donations.manage'))
    
    return render_template('donations/add.html')