from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Product
from utils.barcode import generate_barcode
import uuid
import os

bp = Blueprint('product', __name__)

@bp.route('/products')
@login_required
def index():
    search = request.args.get('q')
    if search:
        products = Product.query.filter(Product.name.ilike(f"%{search}%")).all()
    else:
        products = Product.query.all()
    low_stock_products = [p for p in products if p.quantity < 20]  # Set threshold as needed
    return render_template('index.html', products=products, low_stock_products=low_stock_products)

@bp.route('/add', methods=['GET', 'POST'])
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

        # Generate barcode
        barcode_path = generate_barcode(barcode_value)

        # ✅ Ensure barcode image exists before rendering
        abs_path = os.path.join(current_app.root_path, 'static', 'barcodes', f'{barcode_value}.png')
        barcode_exists = os.path.exists(abs_path)

        return render_template(
            'add_success.html',
            barcode_value=barcode_value,
            product=new_product,
            barcode_exists=barcode_exists,
            from_view=False
        )

    return render_template('add_product.html')

@bp.route('/product/<barcode_value>/barcode')
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


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
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
        return redirect(url_for('product.index'))

    return render_template('edit_product.html', product=product)


@bp.route('/delete/<int:id>')
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully", "success")
    return redirect(url_for('product.index'))

@bp.route('/product/barcode/<barcode>')
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
    

@bp.route('/restock', methods=['GET', 'POST'])
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