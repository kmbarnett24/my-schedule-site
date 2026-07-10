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

# Database Tables
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initials = db.Column(db.String(3), unique=True, nullable=False)
    role = db.Column(db.String(20), default='Staff') # Staff or Manager

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    time_slot = db.Column(db.String(50), nullable=False) # e.g., "7 AM - 7 PM"
    claims = db.relationship('ShiftClaim', backref='shift', cascade="all, delete-orphan")

class ShiftClaim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending Approval') # Pending Approval, Approved
    user = db.relationship('User', backref='claims')

class MonthStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    month_key = db.Column(db.String(7), unique=True, nullable=False) # Format: "YYYY-MM"
    is_finalized = db.Column(db.Boolean, default=False)

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

HOLIDAYS_FIXED = {
    "01-01": "New Year 🎉", "07-04": "4th of July 🎆", 
    "10-31": "Halloween 🎃", "11-11": "Veterans Day 🎖️", 
    "12-25": "Christmas 🎄", "12-31": "NYE ✨"
}

@app.route('/')
def index():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    today = datetime.today()
    year = today.year
    
    month = request.args.get('month', default=today.month, type=int)
    if month < 1 or month > 12:
        month = today.month
        
    month_key = f"{year}-{month:02d}"
    
    start_date_str = f"{year}-{month:02d}-01"
    end_date_str = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    
    db_shifts = Shift.query.filter(Shift.date >= start_date_str, Shift.date <= end_date_str).all()
    
    shifts_by_day = {}
    for shift in db_shifts:
        day_num = int(shift.date.split('-')[2])
        if day_num not in shifts_by_day: shifts_by_day[day_num] = []
        shifts_by_day[day_num].append(shift)

    status_record = MonthStatus.query.filter_by(month_key=month_key).first()
    is_finalized = status_record.is_finalized if status_record else False

    all_users = User.query.filter_by(role='Staff').order_by(User.name).all()
    holidays_by_day = {d: HOLIDAYS_FIXED[f"{month:02d}-{d:02d}"] for d in range(1, 32) if f"{month:02d}-{d:02d}" in HOLIDAYS_FIXED}
    
    cal = calendar.Calendar(firstweekday=6)
    all_months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    
    return render_template('index.html', days=list(cal.itermonthdays(year, month)), 
                           shifts_by_day=shifts_by_day, holidays_by_day=holidays_by_day,
                           theme=MONTH_THEMES[month], month_name=calendar.month_name[month], current_month_num=month,
                           year=year, is_finalized=is_finalized, all_users=all_users, month_key=month_key,
                           all_months_list=all_months_list)

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
        flash('Initials not found.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    shift = Shift.query.get(shift_id)
    if not shift:
        flash('Shift not found.', 'error')
        return redirect(url_for('index'))
        
    month_key = shift.date[:7] # Extracts YYYY-MM directly from shift date
    status_record = MonthStatus.query.filter_by(month_key=month_key).first()
    if status_record and status_record.is_finalized:
        flash('Schedule is locked! Changes cannot be processed for finalized months.', 'error')
        current_view_month = int(month_key.split('-')[1])
        return redirect(url_for('index', month=current_view_month))

    user_id = session['user_id']
    existing_claim = ShiftClaim.query.filter_by(shift_id=shift_id, user_id=user_id).first()
    
    if existing_claim:
        flash('You have already requested a slot on this shift.', 'info')
    else:
        new_claim = ShiftClaim(shift_id=shift_id, user_id=user_id, status='Pending Approval')
        db.session.add(new_claim)
        db.session.commit()
        flash('Sign-up request recorded!', 'success')
        
    current_view_month = int(month_key.split('-')[1])
    return redirect(url_for('index', month=current_view_month))

@app.route('/manager/review-claim/<int:claim_id>/<action>')
def review_claim(claim_id, action):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    claim = ShiftClaim.query.get(claim_id)
    current_view_month = datetime.today().month
    if claim:
        current_view_month = int(claim.shift.date.split('-')[1])
        if action == 'approve':
            claim.status = 'Approved'
        elif action == 'deny':
            db.session.delete(claim)
        db.session.commit()
    return redirect(url_for('index', month=current_view_month))

@app.route('/manager/reassign', methods=['POST'])
def reassign_staff():
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    
    claim_id = request.form.get('claim_id')
    user_id = request.form.get('user_id')
    target_date = request.form.get('target_date')
    target_slot = request.form.get('target_slot')

    target_shift = Shift.query.filter_by(date=target_date, time_slot=target_slot).first()
    if not target_shift:
        flash('Error mapping destination calendar day parameters.', 'error')
        return redirect(url_for('index'))

    current_view_month = int(target_date.split('-')[1])

    if claim_id:
        claim = ShiftClaim.query.get(claim_id)
        if claim:
            claim.shift_id = target_shift.id
            claim.status = 'Approved'
            db.session.commit()
            flash('Staff reassigned successfully!', 'success')
    elif user_id:
        new_claim = ShiftClaim(shift_id=target_shift.id, user_id=user_id, status='Approved')
        db.session.add(new_claim)
        db.session.commit()
        flash('Staff assigned directly to target date block!', 'success')

    return redirect(url_for('index', month=current_view_month))

@app.route('/manager/finalize/<month_key>/<int:status>')
def finalize_month(month_key, status):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    
    record = MonthStatus.query.filter_by(month_key=month_key).first()
    if not record:
        record = MonthStatus(month_key=month_key)
        db.session.add(record)
        
    record.is_finalized = True if status == 1 else False
    db.session.commit()
    
    current_view_month = int(month_key.split('-')[1])
    flash('Schedule updates locked and broadcasted!', 'success')
    return redirect(url_for('index', month=current_view_month))

@app.route('/admin/register', methods=['GET', 'POST'])
def register_staff():
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    if request.method == 'POST':
        full_name = request.form.get('name').strip()
        initials = request.form.get('initials').strip().upper()
        role = request.form.get('role')
        if len(initials) == 3 and not User.query.filter_by(initials=initials).first():
            db.session.add(User(name=full_name, initials=initials, role=role))
            db.session.commit()
    all_users = User.query.order_by(User.role.desc(), User.name).all()
    return render_template('register.html', users=all_users)

@app.route('/seed-database-xyz')
def seed():
    db.drop_all()
    db.create_all()
    
    super_manager = User(name="Head Administrator", initials="ADM", role="Manager")
    db.session.add(super_manager)
    
    today = datetime.today()
    year = today.year
    
    for m in range(1, 13):
        num_days = calendar.monthrange(year, m)[1]
        for day in range(1, num_days + 1):
            day_str = f"{year}-{m:02d}-{day:02d}"
            db.session.add(Shift(date=day_str, time_slot="7 AM - 7 PM"))
            db.session.add(Shift(date=day_str, time_slot="7 PM - 7 AM"))
        
    db.session.commit()
    return "Full 12-month schedule system architecture successfully initialized! Log in with 'ADM'."

# Force-creates any missing database structure blocks on every system startup
with app.app_context(): 
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)