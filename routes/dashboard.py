# dashboard.py
from flask import Blueprint, render_template, request
from flask_login import login_required
from models import db, Product, Sale, Expense
from sqlalchemy import func, extract
from datetime import datetime
from collections import defaultdict

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    # Parse date filters
    start_date_str = request.args.get('start')
    end_date_str = request.args.get('end')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        end_date = None

    # Build filtered queries
    sales_query = Sale.query
    expense_query = Expense.query

    if start_date:
        sales_query = sales_query.filter(Sale.timestamp >= start_date)
        expense_query = expense_query.filter(Expense.expense_date >= start_date)
    if end_date:
        sales_query = sales_query.filter(Sale.timestamp <= end_date)
        expense_query = expense_query.filter(Expense.expense_date <= end_date)

    total_sales = db.session.query(func.sum(Sale.total_price)).filter(Sale.id.in_([s.id for s in sales_query])).scalar() or 0
    total_cogs = db.session.query(func.sum(Sale.cost_price * Sale.quantity)).filter(Sale.id.in_([s.id for s in sales_query])).scalar() or 0
    total_expenses = db.session.query(func.sum(Expense.amount)).filter(Expense.id.in_([e.id for e in expense_query])).scalar() or 0
    total_stock = db.session.query(func.sum(Product.quantity)).scalar() or 0

    profit = total_sales - total_cogs - total_expenses

    # For expense trend chart (grouped monthly)
    expense_trend_query = expense_query.with_entities(
        func.strftime('%Y-%m', Expense.expense_date),  # For SQLite
        func.sum(Expense.amount)
    ).group_by(func.strftime('%Y-%m', Expense.expense_date)).order_by(func.strftime('%Y-%m', Expense.expense_date)).all()

    expense_labels = [row[0] for row in expense_trend_query]
    expense_values = [float(row[1]) for row in expense_trend_query]
    
    
    # For profit trend chart (grouped monthly)
    # Step 1: Sales and COGS grouped by month
    sales_data = sales_query.with_entities(
        func.strftime('%Y-%m', Sale.timestamp).label('month'),
        func.sum(Sale.total_price).label('monthly_sales'),
        func.sum(Sale.cost_price * Sale.quantity).label('monthly_cogs')
    ).group_by('month').order_by('month').all()

    # Step 2: Expenses grouped by month (reuse from expense_trend_query)
    expense_data = {row[0]: float(row[1]) for row in expense_trend_query}

    # Step 3: Merge all into monthly profit
    monthly_profit = defaultdict(lambda: {'sales': 0.0, 'cogs': 0.0, 'expenses': 0.0})

    # Fill in sales and COGS
    for row in sales_data:
        month = row[0]
        monthly_profit[month]['sales'] = float(row[1] or 0)
        monthly_profit[month]['cogs'] = float(row[2] or 0)

    # Fill in expenses
    for month, amount in expense_data.items():
        monthly_profit[month]['expenses'] = amount

    # Step 4: Compute profit per month
    profit_labels = sorted(monthly_profit.keys())
    profit_values = [
        monthly_profit[m]['sales'] - monthly_profit[m]['cogs'] - monthly_profit[m]['expenses']
        for m in profit_labels
    ]


    return render_template("dashboard.html",
        total_sales=total_sales,
        total_expenses=total_expenses,
        total_stock=total_stock,
        total_cogs=total_cogs,
        profit=profit,
        expense_labels=expense_labels,
        expense_values=expense_values,
        profit_labels=profit_labels,
        profit_values=profit_values
    )
