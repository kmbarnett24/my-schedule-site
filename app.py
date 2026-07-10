from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import calendar

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

db_url = os.environ.get('DATABASE_URL', 'sqlite:///schedule.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initials = db.Column(db.String(3), unique=True, nullable=False)
    role = db.Column(db.String(20), default='Staff') # Staff or Manager

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    time_slot = db.Column(db.String(50), nullable=False)
    claimed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='Open')
    claimed_by = db.relationship('User', backref='shifts')

MONTH_THEMES = {
    1: {"bg": "from-blue-900 to-indigo-900", "emoji": "❄️", "sub": "Fresh Starts & New Goals"},
    2: {"bg": "from-rose-500 to-red-600", "emoji": "💖", "sub": "Share the Love & Stay Driven"},
    3: {"bg": "from-emerald-600 to-green-700", "emoji": "🍀", "sub": "Springing Forward Together"},
    4: {"bg": "from-cyan-500 to-teal-600", "emoji": "🌸", "sub": "April Showers & Productive Hours"},
    5: {"bg": "from-amber-500 to-orange-600", "emoji": "☀️", "sub": "Gearing Up for Summer"},
    6: {"bg": "from-sky-400 to-indigo-500", "emoji": "🌊", "sub": "Sunny Days & Smooth Operations"},
    7: {"bg": "from-red-600 to-blue-700", "emoji": "🎆", "sub": "Mid-Summer Hustle"},
    8: {"bg": "from-amber-600 to-yellow-500", "emoji": "🌻", "sub": "Sustaining Our Momentum"},
    9: {"bg": "from-orange-700 to-amber-800", "emoji": "🍂", "sub": "Autumn Shifts & Crisp Air"},
    10: {"bg": "from-purple-800 to-orange-700", "emoji": "🎃", "sub": "Spooky Good Teamwork"},
    11: {"bg": "from-amber-800 to-amber-950", "emoji": "🦃", "sub": "Gratitude & High Performance"},
    12: {"bg": "from-red-700 to-emerald-800", "emoji": "🎄", "sub": "Wrapping Up the Year Strong"}
}

HOLIDAYS_FIXED = {
    "01-01": "New Year's Day 🎉", "07-04": "Independence Day 🎆", 
    "10-31": "Halloween 🎃", "11-11": "Veterans Day 🎖️", 
    "12-25": "Christmas Day 🎄", "12-31": "New Year's Eve ✨"
}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        initials = request.form.get('initials').strip().upper()
        user = User.query.filter_by(initials=initials).first()
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            return redirect(url_for('index'))
        flash('Initials not found. Ask a manager to add you to the panel roster.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
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

# 🆕 NEW WORKSPACE: Secure Manager-Only Staff Directory Registration Panel
@app.route('/admin/register', methods=['GET', 'POST'])
def register_staff():
    if session.get('user_role') != 'Manager':
        flash('Access Denied: Managers only.', 'error')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        full_name = request.form.get('name').strip()
        initials = request.form.get('initials').strip().upper()
        role = request.form.get('role')
        
        # Validation checks
        if len(initials) != 3:
            flash('Error: Initials must be exactly 3 characters.', 'error')
        elif User.query.filter_by(initials=initials).first():
            flash(f'Error: Initials "{initials}" are already taken.', 'error')
        else:
            new_user = User(name=full_name, initials=initials, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash(f'Successfully added {full_name} ({initials}) to the system!', 'success')
            
    # Fetch all registered users to display a complete table roster
    all_users = User.query.order_by(User.role.desc(), User.name).all()
    return render_template('register.html', users=all_users)

@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open':
        shift.claimed_by_id = session['user_id']
        shift.status = 'Pending Approval'
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Pending Approval':
        if action == 'approve': shift.status = 'Approved'
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by_id = None
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/seed-database-xyz')
def seed():
    db.drop_all()
    db.create_all()
    
    # ⚠️ SEEDING ONE SUPER MANAGER INITIAL: Use this initial to log in first and register others!
    super_manager = User(name="Head Administrator", initials="ADM", role="Manager")
    db.session.add(super_manager)
    
    today = datetime.today()
    sample_shifts = [
        Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="Day (7am-7pm)"),
        Shift(date=f"{today.year}-{today.month:02d}-12", time_slot="Night (7pm-7am)"),
        Shift(date=f"{today.year}-{today.month:02d}-15", time_slot="Day (7am-7pm)"),
    ]
    db.session.add_all(sample_shifts)
    db.session.commit()
    return "Database wiped and initialized. Log in using 'ADM' to access the registration dashboard."

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)