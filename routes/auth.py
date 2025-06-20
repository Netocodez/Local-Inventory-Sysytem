from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user
from models import db, User, Sale, Expense, Product
from sqlalchemy import func
from utils.decorators import admin_required, approver_required


bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')

        # Basic validation
        if not username or not full_name or not email or not password:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for('auth.login'))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return redirect(url_for('auth.login'))

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "danger")
            return redirect(url_for('auth.login'))

        if phone_number and User.query.filter_by(phone_number=phone_number).first():
            flash("Phone number already exists.", "danger")
            return redirect(url_for('auth.login'))

        hashed_password = generate_password_hash(password)

        user = User(
            username=username,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            password=hashed_password,
            role='user',          # default role
            is_approved=False     # default not approved
        )

        db.session.add(user)
        db.session.commit()
        flash("User Registered successfully!", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if not user.is_approved:
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('auth.login'))

            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard.dashboard'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    # Clear all flash messages before redirecting
    session.pop('_flashes', None)
    return redirect(url_for('auth.login'))