from flask import Blueprint, render_template, redirect, url_for, flash, send_file, request
from models import db, Expense, Product, Sale, User
import pandas as pd
from utils.decorators import admin_required, approver_required
from flask_login import login_required
from datetime import datetime, timedelta
import io

bp = Blueprint('report', __name__)


@bp.route('/export/products')
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

@bp.route('/export/sales')
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


@bp.route('/export')
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
