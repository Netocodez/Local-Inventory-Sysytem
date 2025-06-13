from flask import Flask, render_template, request, redirect, url_for, send_file, flash, abort, jsonify
from flask_migrate import Migrate
from models import db, Product, Sale, Expense, User,  SaleTransaction
from flask_login import LoginManager, current_user, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from datetime import datetime, timedelta
import io
from functools import wraps
from sqlalchemy import func
import barcode
import uuid
import os
from barcode.writer import ImageWriter
from api import api 
from backup import backup_bp

import sys

app = Flask(__name__)
app.secret_key = 'dev-secret-key-1234'  # Change this!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

# Register blueprint
app.register_blueprint(api)
app.register_blueprint(backup_bp)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

#@app.before_first_request
def create_tables():
    db.create_all()
    

def generate_barcode(data, filename=None, folder='static/barcodes'):
    if not os.path.exists(folder):
        os.makedirs(folder)

    # Use Code128 because it supports letters and numbers
    code128 = barcode.get('code128', data, writer=ImageWriter())

    if not filename:
        filename = f"{data}.png"
    filepath = os.path.join(folder, filename)
    
    code128.save(filepath.replace('.png', ''))  # `save()` auto-appends `.png`
    
    return filepath

    
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def approver_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not (current_user.is_admin() or current_user.is_approver()):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/pending_users')
@login_required
@approver_required
def pending_users():
    users = User.query.filter_by(is_approved=False).all()
    return render_template('pending_users.html', users=users)

@app.route('/admin/approve_user/<int:user_id>', methods=['POST'])
@login_required
@approver_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f"User {user.username} approved.", "success")
    return redirect(url_for('pending_users'))

@app.route('/admin/reject_user/<int:user_id>', methods=['POST'])
@login_required
@approver_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} rejected and deleted.", "info")
    return redirect(url_for('pending_users'))

@app.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin_manage_users.html', users=users)

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
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

        return redirect(url_for('manage_users'))
    
    return render_template('admin_edit_user.html', user=user)


@app.route('/sale/<int:sale_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    products = Product.query.all()

    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])
        cost_price = float(request.form['cost_price'])
        unit_price = float(request.form['unit_price'])
        customer_name = request.form.get('customer_name', '').strip()
        payment_type = request.form.get('payment_type', 'Cash')
        comments = request.form.get('comments', '').strip()

        product = Product.query.get_or_404(product_id)

        # Adjust product quantity stock if product changed or quantity changed
        if sale.product_id != product_id:
            # Return old product stock
            old_product = Product.query.get(sale.product_id)
            if old_product:
                old_product.quantity += sale.quantity

            # Deduct new product stock
            if product.quantity < quantity:
                flash("Insufficient stock for selected product.", "danger")
                return redirect(request.url)
            product.quantity -= quantity

        else:
            # If same product, adjust stock by difference
            diff = quantity - sale.quantity
            if diff > 0 and product.quantity < diff:
                flash("Insufficient stock to increase quantity.", "danger")
                return redirect(request.url)
            product.quantity -= diff

        sale.product_id = product_id
        sale.quantity = quantity
        sale.cost_price = cost_price
        sale.unit_price = unit_price
        sale.total_price = unit_price * quantity
        sale.customer_name = customer_name or None
        sale.payment_type = payment_type
        sale.comments = comments or None

        db.session.commit()
        flash("Sale updated successfully!", "success")
        return redirect(url_for('sales_list'))

    return render_template('edit_sale.html', sale=sale, products=products)

@app.route('/transaction/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_transaction(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()
    transaction = SaleTransaction.query.get_or_404(transaction_id)
    products = Product.query.all()

    if not sales:
        flash("Transaction not found.", "danger")
        return redirect(url_for('sales_list'))

    if request.method == 'POST':
        for sale in sales:
            form_prefix = f"sale_{sale.id}"
            product_id = int(request.form.get(f'{form_prefix}_product_id', sale.product_id))
            quantity = int(request.form.get(f'{form_prefix}_quantity', sale.quantity))
            cost_price = float(request.form.get(f'{form_prefix}_cost_price', sale.cost_price))
            unit_price = float(request.form.get(f'{form_prefix}_unit_price', sale.unit_price))
            customer_name = request.form.get(f'{form_prefix}_customer_name', sale.customer_name)
            payment_type = request.form.get(f'{form_prefix}_payment_type', sale.payment_type)

            product = Product.query.get_or_404(product_id)

            # Stock adjustment logic
            if sale.product_id != product_id:
                old_product = Product.query.get(sale.product_id)
                if old_product:
                    old_product.quantity += sale.quantity

                if product.quantity < quantity:
                    flash(f"Insufficient stock for product {product.name}.", "danger")
                    return redirect(request.url)
                product.quantity -= quantity
            else:
                diff = quantity - sale.quantity
                if diff > 0 and product.quantity < diff:
                    flash(f"Insufficient stock to increase quantity for {product.name}.", "danger")
                    return redirect(request.url)
                product.quantity -= diff

            # Update sale
            sale.product_id = product_id
            sale.quantity = quantity
            sale.cost_price = cost_price
            sale.unit_price = unit_price
            sale.total_price = unit_price * quantity
            sale.customer_name = customer_name or None
            sale.payment_type = payment_type

        # Save transaction-level comments
        transaction.comments = request.form.get('transaction_comments', '')

        db.session.commit()
        flash("Transaction updated successfully!", "success")
        return redirect(url_for('sales_list', transaction_id=transaction_id))

    return render_template('edit_transaction.html',
                           sales=sales,
                           products=products,
                           transaction_id=transaction_id,
                           transaction_comments=transaction.comments)



@app.route('/sale/<int:sale_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    product = Product.query.get(sale.product_id)

    # Return stock quantity
    if product:
        product.quantity += sale.quantity

    db.session.delete(sale)
    db.session.commit()

    flash("Sale deleted successfully!", "success")
    return redirect(url_for('sales_list'))

@app.route('/transaction/<int:transaction_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_transaction(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()

    if not sales:
        flash("Transaction not found.", "danger")
        return redirect(url_for('sales_list'))

    for sale in sales:
        product = Product.query.get(sale.product_id)
        if product:
            product.quantity += sale.quantity
        db.session.delete(sale)

    db.session.commit()
    flash("Transaction deleted successfully!", "success")
    return redirect(url_for('sales_list'))


@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')

        # Basic validation
        if not username or not full_name or not email or not password:
            return "Please fill all required fields", 400

        if User.query.filter_by(username=username).first():
            return "Username already exists", 400

        if User.query.filter_by(email=email).first():
            return "Email already exists", 400

        if phone_number and User.query.filter_by(phone_number=phone_number).first():
            return "Phone number already exists", 400

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
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if not user.is_approved:
                flash('Your account is pending admin approval.', 'warning')
                return redirect(url_for('login'))

            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    total_sales = db.session.query(db.func.sum(Sale.total_price)).scalar() or 0
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    total_stock = db.session.query(db.func.sum(Product.quantity)).scalar() or 0
    total_cogs = db.session.query(func.sum(Sale.cost_price * Sale.quantity)).scalar() or 0
    
    profit = total_sales - total_cogs - total_expenses

    return render_template('dashboard.html', 
                           total_sales=total_sales, 
                           total_expenses=total_expenses, 
                           total_stock=total_stock,
                           profit=profit)

@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        expense_date_str = request.form.get('expense_date')
        try:
            expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date() if expense_date_str else datetime.utcnow().date()
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return redirect(url_for('expenses'))
        new_expense = Expense(description=description, amount=amount, expense_date=expense_date)
        db.session.add(new_expense)
        db.session.commit()
        flash("Expense updated successfully", "success")
        return redirect(url_for('expenses'))

    expenses = Expense.query.all()
    return render_template('expenses.html', expenses=expenses)

@app.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if request.method == 'POST':
        expense.description = request.form['description']
        expense.amount = float(request.form['amount'])
        expense_date_str = request.form.get('expense_date')
        if expense_date_str:
            try:
                expense.expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
                return render_template('edit_expense.html', expense=expense)
        db.session.commit()
        flash("Expense updated successfully", "success")
        return redirect(url_for('expenses'))

    return render_template('edit_expense.html', expense=expense)

@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully", "success")
    return redirect(url_for('expenses'))



@app.route('/products')
@login_required
def index():
    search = request.args.get('q')
    if search:
        products = Product.query.filter(Product.name.ilike(f"%{search}%")).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form['quantity'])
        cost_price = float(request.form['cost_price'])
        price = float(request.form['price'])
        barcode_value = request.form.get('barcode')

        if not barcode_value:
            barcode_value = str(uuid.uuid4())[:12].upper()

        new_product = Product(
            name=name,
            quantity=quantity,
            cost_price=cost_price,
            price=price,
            barcode=barcode_value
        )
        db.session.add(new_product)
        db.session.commit()

        barcode_path = generate_barcode(barcode_value)  # Save barcode image

        # Render confirmation page with barcode
        return render_template('add_success.html', barcode_value=barcode_value)

    return render_template('add_product.html')

@app.route('/product/<barcode_value>/barcode')
def view_barcode(barcode_value):
    barcode_path = os.path.join('static', 'barcodes', f'{barcode_value}.png')
    barcode_exists = os.path.exists(barcode_path)

    product = Product.query.filter_by(barcode=barcode_value).first()

    return render_template(
        'add_success.html',
        product=product,
        barcode_value=barcode_value,
        barcode_exists=barcode_exists,
        from_view=True  # distinguish from actual add
    )


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)

    if request.method == 'POST':
        product.name = request.form['name']
        product.quantity = int(request.form['quantity'])
        product.cost_price = float(request.form['cost_price'])
        product.price = float(request.form['price'])

        input_barcode = request.form.get('barcode', '').strip()

        if not input_barcode:
            input_barcode = str(uuid.uuid4())[:12].upper()

        existing = Product.query.filter(Product.barcode == input_barcode, Product.id != product.id).first()
        if existing:
            flash("Error: Barcode already in use by another product.", "danger")
            return render_template('edit_product.html', product=product)

        product.barcode = input_barcode

        # ✅ Generate barcode image before saving
        generate_barcode(input_barcode)

        db.session.commit()
        flash("Product edited successfully", "success")
        return redirect(url_for('index'))

    return render_template('edit_product.html', product=product)


@app.route('/delete/<int:id>')
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully", "success")
    return redirect(url_for('index'))

@app.route('/product/barcode/<barcode>')
@login_required
def get_product_by_barcode(barcode):
    product = Product.query.filter_by(barcode=barcode).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    return jsonify({
        'id': product.id,
        'name': product.name,
        'price': product.price,
        'cost_price': product.cost_price,
        'quantity': product.quantity
    })

@app.route('/sale', methods=['GET', 'POST'])
@login_required
def record_sale():
    products = Product.query.all()
    if request.method == 'POST':
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        cost_prices = request.form.getlist('cost_price[]')
        unit_prices = request.form.getlist('unit_price[]')

        customer_name = request.form.get('customer_name', '').strip()
        payment_type = request.form.get('payment_type', 'Cash')
        comments = request.form.get('comments', '').strip()

        # Create the transaction header
        transaction = SaleTransaction(
            customer_name=customer_name or None,
            payment_type=payment_type,
            comments=comments or None,
            user_id=current_user.id
        )
        db.session.add(transaction)
        db.session.flush()  # Flush to get transaction.id

        for i in range(len(product_ids)):
            product = Product.query.get_or_404(int(product_ids[i]))
            quantity = int(quantities[i])
            cost_price = float(cost_prices[i])
            unit_price = float(unit_prices[i])

            if product.quantity < quantity:
                db.session.rollback()
                return f"Insufficient stock for product: {product.name}", 400

            sale = Sale(
                product_id=product.id,
                quantity=quantity,
                cost_price=cost_price,
                unit_price=unit_price,
                total_price=unit_price * quantity,
                customer_name=customer_name or None,
                payment_type=payment_type,
                comments=comments or None,
                user_id=current_user.id,
                transaction_id=transaction.id
            )
            product.quantity -= quantity
            db.session.add(sale)

        db.session.commit()
        flash("Sales recorded successfully!", "success")
        return redirect(url_for('sales_list', transaction_id=transaction.id))

    return render_template('record_sale.html', products=products)


@app.route('/test_user')
@login_required
def test_user():
    # current logged-in user info
    current_user_info = {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email,
    }

    # get all sales with user info
    sales = Sale.query.all()
    sales_data = []
    for sale in sales:
        sales_data.append({
            "sale_id": sale.id,
            "product": sale.product.name,
            "quantity": sale.quantity,
            "total_price": sale.total_price,
            "sold_by_username": sale.user.username if sale.user else None,
            "sold_by_full_name": sale.user.full_name if sale.user else None,
        })

    return jsonify({
        "current_user": current_user_info,
        "sales": sales_data,
    })



@app.route('/receipt/<int:sale_id>')
@login_required
def view_receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    product = Product.query.get(sale.product_id)
    return render_template('receipt.html', sale=sale, product=product)

@app.route('/receipt/transaction/<int:transaction_id>')
@login_required
def view_transaction_receipt(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()
    if not sales:
        abort(404)

    # Optional: Fetch extra info like the first sale's customer, payment, etc.
    product_ids = [sale.product_id for sale in sales]
    products = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}

    return render_template('transaction_receipt.html', sales=sales, products=products)



from collections import defaultdict

@app.route('/sales')
@login_required
def sales_list():
    search = request.args.get('q', '').strip()
    sales_query = Sale.query.join(Product, Sale.product_id == Product.id)

    if search:
        if search.isdigit():
            sales_query = sales_query.filter(
                (Sale.transaction_id == int(search)) |
                (Product.name.ilike(f"%{search}%"))
            )
        else:
            sales_query = sales_query.filter(Product.name.ilike(f"%{search}%"))

    sales_query = sales_query.order_by(Sale.transaction_id.desc(), Sale.timestamp.desc())
    sales = sales_query.all()

    # Group by transaction_id
    grouped_sales = defaultdict(list)
    for s in sales:
        grouped_sales[s.transaction_id].append({
            'id': s.id,
            'product_name': s.product.name if s.product else "Unknown",
            'quantity': s.quantity,
            'unit_price': s.unit_price,
            'total_price': s.total_price,
            'customer_name': s.customer_name,
            'payment_type': s.payment_type,
            'comments': s.comments,
            'timestamp': s.timestamp,
            'username': s.user.username if s.user else "-",
        })

    # Optional: Get transaction info per transaction_id
    transactions = SaleTransaction.query.filter(SaleTransaction.id.in_(grouped_sales.keys())).all()
    transaction_info = {t.id: t for t in transactions}

    return render_template('sales_list.html', grouped_sales=grouped_sales, transaction_info=transaction_info)


@app.route('/expense', methods=['GET', 'POST'])
@login_required
def record_expense():
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        expense_date_str = request.form.get('expense_date')
        try:
            expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date()
        except:
            expense_date = datetime.utcnow().date()  # Fallback
        expense = Expense(description=description, amount=amount, expense_date=expense_date)
        db.session.add(expense)
        db.session.commit()
        flash("Expense updated successfully", "success")
        return redirect(url_for('expenses'))
    return render_template('record_expense.html')

@app.route('/export/products')
@login_required
def export_products():
    products = Product.query.all()
    data = [{'Name': p.name, 'Quantity': p.quantity, 'Price': p.price} for p in products]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Products')
    output.seek(0)
    flash("Products exported successfully!", "success")
    return send_file(output, as_attachment=True, download_name='products.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/export/sales')
@login_required
def export_sales():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None
    except ValueError:
        start_date = end_date = None

    sales_query = Sale.query
    if start_date:
        sales_query = sales_query.filter(Sale.timestamp >= start_date)
    if end_date:
        sales_query = sales_query.filter(Sale.timestamp < end_date + timedelta(days=1))

    sales = sales_query.all()
    data = []
    for sale in sales:
        product = Product.query.get(sale.product_id)
        data.append({
            'Sale Id': sale.id,
            'Transaction ID': sale.transaction_id,  # ✅ Add this line
            'Product': product.name if product else 'Unknown',
            'Quantity': sale.quantity,
            'Unit Price': sale.unit_price,
            'Total Price': sale.total_price,
            'Customer Name': sale.customer_name,
            'Payment Type': sale.payment_type,
            'Comments': sale.comments,
            'Sold By': sale.user.username if sale.user else 'N/A',
            'Timestamp': sale.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sales')
    output.seek(0)
    flash("Selected sales exported successfully!", "success")
    return send_file(output, as_attachment=True, download_name='sales.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/export')
@login_required
def export_reports():
    # Get optional start and end date from query params
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Parse dates if provided
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None
    except ValueError:
        start_date = end_date = None  # Ignore bad format

    # Base query
    sales_query = Sale.query

    # Apply date filter if available
    if start_date:
        sales_query = sales_query.filter(Sale.timestamp >= start_date)
    if end_date:
        # To include the end_date whole day, add one day and use less than that
        sales_query = sales_query.filter(Sale.timestamp < end_date + timedelta(days=1))

    #Order by latest first
    sales_query = sales_query.order_by(Sale.timestamp.desc(), Sale.id.desc())
    sales = sales_query.all()

    sales_data = []
    for s in sales:
        product = Product.query.get(s.product_id)
        sales_data.append({
            'id': s.id,
            'transaction_id': s.transaction_id,
            'product_name': product.name if product else "Unknown Product",
            'quantity': s.quantity,
            'unit_price': s.unit_price,
            'total_price': s.total_price,
            'comments': s.comments,
            'username': s.user.username if s.user else '',
            'timestamp': s.timestamp.strftime("%Y-%m-%d") if s.timestamp else ''
        })

    return render_template('export_reports.html', sales=sales_data, start_date=start_date_str or '', end_date=end_date_str or '')

@app.route('/restock', methods=['GET', 'POST'])
@login_required
def restock_product():
    products = Product.query.all()
    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        additional_quantity = int(request.form['quantity'])
        new_price = float(request.form['price'])

        product = Product.query.get_or_404(product_id)
        product.quantity += additional_quantity
        product.price = new_price  # update price to new value
        db.session.commit()
        flash("Product restocked successfully!", "success")
        return redirect(url_for('index'))

    return render_template('restock_product.html', products=products)


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
