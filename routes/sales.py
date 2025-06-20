from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from models import db, Product, Sale, SaleTransaction
from utils.decorators import admin_required, approver_required
from collections import defaultdict

bp = Blueprint('sales', __name__)


@bp.route('/sales')
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

@bp.route('/sale', methods=['GET', 'POST'])
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
        return redirect(url_for('sales.sales_list', transaction_id=transaction.id)) #q=transaction.id

    return render_template('record_sale.html', products=products)

@bp.route('/receipt/<int:sale_id>')
@login_required
def view_receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    product = Product.query.get(sale.product_id)
    return render_template('receipt.html', sale=sale, product=product)

@bp.route('/receipt/transaction/<int:transaction_id>')
@login_required
def view_transaction_receipt(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()
    if not sales:
        abort(404)

    # Optional: Fetch extra info like the first sale's customer, payment, etc.
    product_ids = [sale.product_id for sale in sales]
    products = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}

    return render_template('transaction_receipt.html', sales=sales, products=products)

@bp.route('/sale/<int:sale_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('sales.sales_list'))

    return render_template('edit_sale.html', sale=sale, products=products)

@bp.route('/transaction/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_transaction(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()
    transaction = SaleTransaction.query.get_or_404(transaction_id)
    products = Product.query.all()

    if not sales:
        flash("Transaction not found.", "danger")
        return redirect(url_for('sales.sales_list'))

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
        return redirect(url_for('sales.sales_list', transaction_id=transaction_id))

    return render_template('edit_transaction.html',
                           sales=sales,
                           products=products,
                           transaction_id=transaction_id,
                           transaction_comments=transaction.comments)



@bp.route('/sale/<int:sale_id>/delete', methods=['POST'])
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
    return redirect(url_for('sales.sales_list'))

@bp.route('/transaction/<int:transaction_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_transaction(transaction_id):
    sales = Sale.query.filter_by(transaction_id=transaction_id).all()

    if not sales:
        flash("Transaction not found.", "danger")
        return redirect(url_for('sales.sales_list'))

    for sale in sales:
        product = Product.query.get(sale.product_id)
        if product:
            product.quantity += sale.quantity
        db.session.delete(sale)

    db.session.commit()
    flash("Transaction deleted successfully!", "success")
    return redirect(url_for('sales.sales_list'))