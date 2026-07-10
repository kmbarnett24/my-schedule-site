from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import calendar

app = Flask(__name__)
# Secure secret key for user log-in sessions
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

# Direct database connection string for Render/Supabase
db_url = os.environ.get('DATABASE_URL', 'sqlite:///schedule.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Tables
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initials = db.Column(db.String(3), unique=True, nullable=False) # 3 Initials Only
    role = db.Column(db.String(20), default='Staff') # Staff or Manager

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    time_slot = db.Column(db.String(50), nullable=False)
    claimed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='Open') # Open, Pending Approval, Approved
    claimed_by = db.relationship('User', backref='shifts')

# Custom Monthly Themes for the Graphic Banner
MONTH_THEMES = {
    1:  {"bg": "from-blue-900 to-indigo-900", "emoji": "❄️", "sub": "Fresh Starts & New Goals"},
    2:  {"bg": "from-rose-500 to-red-600",     "emoji": "💖", "sub": "Share the Love & Stay Driven"},
    3:  {"bg": "from-emerald-600 to-green-700", "emoji": "🍀", "sub": "Springing Forward Together"},
    4:  {"bg": "from-cyan-500 to-teal-600",    "emoji": "🌸", "sub": "April Showers & Productive Hours"},
    5:  {"bg": "from-amber-500 to-orange-600", "emoji": "☀️", "sub": "Gearing Up for Summer"},
    6:  {"bg": "from-sky-400 to-indigo-500",   "emoji": "🌊", "sub": "Sunny Days & Smooth Operations"},
    7:  {"bg": "from-red-600 to-blue-700",     "emoji": "🎆", "sub": "Mid-Summer Hustle"},
    8:  {"bg": "from-amber-600 to-yellow-500", "emoji": "🌻", "sub": "Sustaining Our Momentum"},
    9:  {"bg": "from-orange-700 to-amber-800", "emoji": "🍂", "sub": "Autumn Shifts & Crisp Air"},
    10: {"bg": "from-purple-800 to-orange-700", "emoji": "🎃", "sub": "Spooky Good Teamwork"},
    11: {"bg": "from-amber-800 to-amber-950",  "emoji": "🦃", "sub": "Gratitude & High Performance"},
    12: {"bg": "from-red-700 to-emerald-800",  "emoji": "🎄", "sub": "Wrapping Up the Year Strong"}
}

# Recognized Calendar Holidays
HOLIDAYS_FIXED = {
    "01-01": "New Year 🎉", "07-04": "4th of July 🎆", 
    "10-31": "Halloween 🎃", "11-11": "Veterans Day 🎖️", 
    "12-25": "Christmas 🎄", "12-31": "NYE ✨"
}

# 1. Main Home Calendar Route
@app.route('/')
def index():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    today = datetime.today()
    year, month = today.year, today.month
    
    start_date_str = f"{year}-{month:02d}-01"
    end_date_str = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    db_shifts = Shift.query.filter(Shift.date >= start_date_str, Shift.date <= end_date_str).all()
    
    shifts_by_day = {}
    for shift in db_shifts:
        day_num = int(shift.date.split('-')[2])
        if day_num not in shifts_by_day: shifts_by_day[day_num] = []
        shifts_by_day[day_num].append(shift)

    holidays_by_day = {d: HOLIDAYS_FIXED[f"{month:02d}-{d:02d}"] for d in range(1, 32) if f"{month:02d}-{d:02d}" in HOLIDAYS_FIXED}
    cal = calendar.Calendar(firstweekday=6)
    
    return render_template('index.html', days=list(cal.itermonthdays(year, month)), 
                           shifts_by_day=shifts_by_day, holidays_by_day=holidays_by_day,
                           theme=MONTH_THEMES[month], month_name=calendar.month_name[month], year=year)

# 2. 3-Initial Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        initials = request.form.get('initials').strip().upper()
        user = User.query.filter_by(initials=initials).first()
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash('Signed in successfully!', 'success')
            return redirect(url_for('index'))
        flash('Initials not found. Ask your manager to add you.', 'error')
    return render_template('login.html')

# 3. Manager Staff Registration Panel
@app.route('/admin/register', methods=['GET', 'POST'])
def register_staff():
    if session.get('user_role') != 'Manager':
        flash('Access Denied: Managers only.', 'error')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        full_name = request.form.get('name').strip()
        initials = request.form.get('initials').strip().upper()
        role = request.form.get('role')
        
        if len(initials) != 3:
            flash('Error: Initials must be exactly 3 letters.', 'error')
        elif User.query.filter_by(initials=initials).first():
            flash(f'Error: Initials "{initials}" are already in use.', 'error')
        else:
            new_user = User(name=full_name, initials=initials, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash(f'Registered {full_name} ({initials}) successfully!', 'success')
            
    all_users = User.query.order_by(User.role.desc(), User.name).all()
    return render_template('register.html', users=all_users)

# 4. Claim Shift Route
@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open':
        shift.claimed_by_id = session['user_id']
        shift.status = 'Pending Approval'
        db.session.commit()
        flash('Shift claimed! Awaiting manager approval.', 'success')
    return redirect(url_for('index'))

# 5. Manager Review Approvals Route
@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Pending Approval':
        if action == 'approve':
            shift.status = 'Approved'
            flash('Shift approved!', 'success')
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by_id = None
            flash('Shift denied and put back open.', 'info')
        db.session.commit()
    return redirect(url_for('index'))

# 6. Logout Route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 7. First-Time Database Setup Tool
@app.route('/seed-database-xyz')
def seed():
    db.drop_all()
    db.create_all()
    
    # Creates one Master Manager account to start out with
    super_manager = User(name="Head Administrator", initials="ADM", role="Manager")
    db.session.add(super_manager)
    
    today = datetime.today()
    # Generates standard nursing shifts on calendar blocks for testing
    sample_shifts = [
        Shift(date=f"{today.year}-{today.month:02d}-01", time_slot="7 AM - 7 PM"),
        Shift(date=f"{today.year}-{today.month:02d}-04", time_slot="7 PM - 7 AM"),
        Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="7 AM - 7 PM"),
        Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="7 PM - 7 AM"),
        Shift(date=f"{today.year}-{today.month:02d}-25", time_slot="7 AM - 7 PM"),
    ]
    db.session.add_all(sample_shifts)
    db.session.commit()
    return "Database updated! Go back to the website and log in using 'ADM'."

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)