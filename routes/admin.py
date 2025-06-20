from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required
from models import db, User
from utils.decorators import admin_required, approver_required

bp = Blueprint('admin', __name__)


@bp.route('/admin/pending_users')
@login_required
@approver_required
def pending_users():
    users = User.query.filter_by(is_approved=False).all()
    return render_template('pending_users.html', users=users)

@bp.route('/admin/approve_user/<int:user_id>', methods=['POST'])
@login_required
@approver_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f"User {user.username} approved.", "success")
    return redirect(url_for('admin.pending_users'))

@bp.route('/admin/reject_user/<int:user_id>', methods=['POST'])
@login_required
@approver_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} rejected and deleted.", "info")
    return redirect(url_for('admin.pending_users'))

@bp.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin_manage_users.html', users=users)

@bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        # Extract data
        new_role = request.form.get('role')
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')
        is_approved = request.form.get('is_approved') == 'on'

        # Update user attributes

        user.role = new_role        
        user.username = username
        user.full_name = full_name
        user.email = email
        user.phone_number = phone_number
        user.is_approved = is_approved

        # Hash password if provided
        if password:
            user.password = generate_password_hash(password)

        try:
            db.session.commit()
            flash(f"Updated user {user.username} successfully.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating user: {str(e)}", "danger")

        return redirect(url_for('admin.manage_users'))
    
    return render_template('admin_edit_user.html', user=user)