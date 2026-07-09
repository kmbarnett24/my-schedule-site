from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.secret_key = 'super-secret-key-123'

# This uses a local database file so we don't have to worry about Supabase passwords
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///schedule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)
    time_slot = db.Column(db.String(50), nullable=False)
    claimed_by = db.Column(db.String(100), default=None, nullable=True)
    status = db.Column(db.String(20), default='Open')

@app.route('/')
def index():
    # Automatically build database tables if they don't exist yet
    db.create_all()
    
    # Pre-populate sample shifts automatically if the system is brand empty
    if Shift.query.count() == 0:
        sample_shifts = [
            Shift(date="2026-08-10", time_slot="09:00 AM - 05:00 PM"),
            Shift(date="2026-08-10", time_slot="05:00 PM - 01:00 AM"),
            Shift(date="2026-08-11", time_slot="09:00 AM - 05:00 PM"),
        ]
        db.session.add_all(sample_shifts)
        db.session.commit()

    shifts = Shift.query.order_by(Shift.date).all()
    return render_template('index.html', shifts=shifts)

@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    staff_name = request.form.get('staff_name')
    staff_email = request.form.get('staff_email')
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open':
        shift.claimed_by = f"{staff_name} ({staff_email})"
        shift.status = 'Pending Approval'
        db.session.commit()
        flash('Shift claimed! Awaiting manager approval.', 'success')
    return redirect(url_for('index'))

@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Pending Approval':
        if action == 'approve':
            shift.status = 'Approved'
            flash('Shift approved!', 'success')
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by = None
            flash('Shift denied and reopened.', 'info')
        db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)