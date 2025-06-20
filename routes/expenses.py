from flask import Blueprint, render_template, redirect, url_for, flash, request
from models import db, Expense
from utils.decorators import admin_required, approver_required
from flask_login import login_required
from datetime import datetime

bp = Blueprint('expense', __name__)


@bp.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        expense_date_str = request.form.get('expense_date')
        try:
            expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date() if expense_date_str else datetime.utcnow().date()
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return redirect(url_for('expense.expenses'))
        new_expense = Expense(description=description, amount=amount, expense_date=expense_date)
        db.session.add(new_expense)
        db.session.commit()
        flash("Expense updated successfully", "success")
        return redirect(url_for('expense.expenses'))

    expenses = Expense.query.all()
    return render_template('expenses.html', expenses=expenses)

@bp.route('/expense', methods=['GET', 'POST'])
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
        return redirect(url_for('expense.expenses'))
    return render_template('record_expense.html')

@bp.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
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
        return redirect(url_for('expense.expenses'))

    return render_template('edit_expense.html', expense=expense)

@bp.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully", "success")
    return redirect(url_for('expense.expenses'))