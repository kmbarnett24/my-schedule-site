from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import calendar

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

# Database Setup
db_url = os.environ.get('DATABASE_URL', 'sqlite:///schedule.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    role = db.Column(db.String(20), default='Staff') # Staff or Manager

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    time_slot = db.Column(db.String(50), nullable=False) # e.g., "Day Shift (9am-5pm)"
    claimed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='Open') # Open, Pending, Approved

    claimed_by = db.relationship('User', backref='shifts')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email not found. Contact management to add your profile.', 'error')
    return render_template('login.html')

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have logged out.', 'info')
    return redirect(url_for('login'))

# Interactive Calendar Dashboard
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Generate a visual calendar for the current month
    today = datetime.today()
    year, month = today.year, today.month
    
    # Get all database shifts for this month
    start_date_str = f"{year}-{month:02d}-01"
    end_date_str = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    
    db_shifts = Shift.query.filter(Shift.date >= start_date_str, Shift.date <= end_date_str).all()
    
    # Group shifts by day for easy front-end parsing
    shifts_by_day = {}
    for shift in db_shifts:
        day_num = int(shift.date.split('-')[2])
        if day_num not in shifts_by_day:
            shifts_by_day[day_num] = []
        shifts_by_day[day_num].append(shift)

    # Calendar generation arrays
    cal = calendar.Calendar(firstweekday=6) # Start weeks on Sunday
    month_days = cal.itermonthdays(year, month)
    month_name = calendar.month_name[month]

    return render_template('index.html', 
                           days=list(month_days), 
                           shifts_by_day=shifts_by_day, 
                           month_name=month_name, 
                           year=year)

# Claim Shift Click Action
@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open':
        shift.claimed_by_id = session['user_id']
        shift.status = 'Pending Approval'
        db.session.commit()
        flash('Shift claimed! Awaiting manager approval.', 'success')
    return redirect(url_for('index'))

# Manager Control Direct Actions
@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    if session.get('user_role') != 'Manager':
        flash('Access Denied.', 'error')
        return redirect(url_for('index'))
        
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Pending Approval':
        if action == 'approve':
            shift.status = 'Approved'
            flash('Shift approved!', 'success')
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by_id = None
            flash('Shift request denied and reopened.', 'info')
        db.session.commit()
    return redirect(url_for('index'))

# Custom setup route to populate users and open mock shifts
@app.route('/seed-database-xyz')
def seed():
    db.create_all()
    if User.query.count() == 0:
        # Create test users
        mgr = User(name="Alice Manager", email="manager@company.com", role="Manager")
        emp1 = User(name="John Staff", email="john@company.com", role="Staff")
        emp2 = User(name="Sarah Staff", email="sarah@company.com", role="Staff")
        db.session.add_all([mgr, emp1, emp2])
        
        # Create sample shifts for the current month
        today = datetime.today()
        sample_shifts = [
            Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="Day (9am-5pm)"),
            Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="Night (5pm-1am)"),
            Shift(date=f"{today.year}-{today.month:02d}-15", time_slot="Day (9am-5pm)"),
            Shift(date=f"{today.year}-{today.month:02d}-20", time_slot="Day (9am-5pm)"),
        ]
        db.session.add_all(sample_shifts)
        db.session.commit()
        return "Database successfully populated with staff login credentials and monthly shifts!"
    return "Database has already been seeded."

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)