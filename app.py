from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

# Pull the production database URL from the environment config
db_url = os.environ.get('DATABASE_URL', 'sqlite:///schedule.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
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

# Helper setup route to quickly populate your calendar empty slots
@app.route('/seed-database-xyz')
def seed():
    db.create_all()
    if Shift.query.count() == 0:
        sample_shifts = [
            Shift(date="2026-08-10", time_slot="09:00 AM - 05:00 PM"),
            Shift(date="2026-08-10", time_slot="05:00 PM - 01:00 AM"),
            Shift(date="2026-08-11", time_slot="09:00 AM - 05:00 PM"),
        ]
        db.session.add_all(sample_shifts)
        db.session.commit()
        return "Database Initialized with Shifts!"
    return "Database already has records."

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)