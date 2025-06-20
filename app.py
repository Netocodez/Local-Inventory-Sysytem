from flask import Flask, render_template, request, redirect, url_for, send_file, flash, abort, jsonify
from flask_migrate import Migrate
from models import db, Product, Sale, Expense, User,  SaleTransaction
from flask_login import LoginManager, current_user, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from api import api 
from backup import backup_bp
from routes import admin, sales, expenses, products, reports, auth, dashboard

app = Flask(__name__)
app.secret_key = 'dev-secret-key-1234'  # Change this!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

# Register blueprint
app.register_blueprint(api)
app.register_blueprint(backup_bp)
app.register_blueprint(admin.bp)
app.register_blueprint(sales.bp)
app.register_blueprint(expenses.bp)
app.register_blueprint(products.bp)
app.register_blueprint(reports.bp)
app.register_blueprint(auth.bp)
app.register_blueprint(dashboard.bp)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

#@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin', role='admin').first():
            admin = User(
                full_name='Developer', 
                email='netocodez@gmail.com', 
                username='admin', 
                password=generate_password_hash('yourpassword'), 
                role='admin', 
                is_approved=True
            )
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, port=5000)
