from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import calendar
import csv
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-dev-key-123')

db_url = os.environ.get('DATABASE_URL', 'sqlite:///schedule.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Structures
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initials = db.Column(db.String(3), unique=True, nullable=False)
    role = db.Column(db.String(20), default='Staff')        # Staff or Manager
    title = db.Column(db.String(30), default='Nurse')       # Nurse, Unit Clerk, Nurse Tech
    preferred_shift = db.Column(db.String(10), default='Day') # Day or Night
    standing_schedules = db.relationship('StandingSchedule', backref='user', cascade="all, delete-orphan")

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)        # Format: YYYY-MM-DD
    time_slot = db.Column(db.String(50), nullable=False)   # "7 AM - 7 PM" or "7 PM - 7 AM"
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

class StandingSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)    # 0=Monday, 6=Sunday
    time_slot = db.Column(db.String(50), nullable=False)   # "7 AM - 7 PM" or "7 PM - 7 AM"

MONTH_THEMES = {
    1: {"bg": "from-blue-900 to-indigo-900", "emoji": "❄️", "sub": "Fresh Starts & New Goals"},
    2: {"bg": "from-rose-500 to-red-600", "emoji": "💖", "sub": "Share the Love"},
    3: {"bg": "from-emerald-600 to-green-700", "emoji": "🍀", "sub": "Springing Forward Together"},
    4: {"bg": "from-cyan-500 to-teal-600", "emoji": "🌸", "sub": "April Productive Hours"},
    5: {"bg": "from-amber-500 to-orange-600", "emoji": "☀️", "sub": "Gearing Up for Summer"},
    6: {"bg": "from-sky-400 to-indigo-500", "emoji": "🌊", "sub": "Sunny Days Operations"},
    7: {"bg": "from-red-600 to-blue-700", "emoji": "🎆", "sub": "Mid-Summer Hustle"},
    8: {"bg": "from-amber-600 to-yellow-500", "emoji": "🌻", "sub": "Sustaining Our Momentum"},
    9: {"bg": "from-orange-700 to-amber-800", "emoji": "🍂", "sub": "Autumn Shifts & Crisp Air"},
    10: {"bg": "from-purple-800 to-orange-700", "emoji": "🎃", "sub": "Spooky Good Teamwork"},
    11: {"bg": "from-amber-800 to-amber-950", "emoji": "🦃", "sub": "Gratitude & Performance"},
    12: {"bg": "from-red-700 to-emerald-800", "emoji": "🎄", "sub": "Wrapping Up Strong"}
}

HOLIDAYS_FIXED = {
    "01-01": "New Year 🎉", "07-04": "4th of July 🎆", "10-31": "Halloween 🎃",
    "11-11": "Veterans Day 🎖️", "12-25": "Christmas 🎄", "12-31": "NYE ✨"
}

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
        
    today = datetime.today()
    year = today.year
    month = request.args.get('month', default=today.month, type=int)
    if month < 1 or month > 12: month = today.month
        
    month_key = f"{year}-{month:02d}"
    start_date_str = f"{year}-{month:02d}-01"
    end_date_str = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    
    db_shifts = Shift.query.filter(Shift.date >= start_date_str, Shift.date <= end_date_str).all()
    
    shifts_by_day = {}
    for shift in db_shifts:
        day_num = int(shift.date.split('-')[2])
        if day_num not in shifts_by_day: shifts_by_day[day_num] = []
        shifts_by_day[day_num].append(shift)

    daily_metrics = {}
    for d in range(1, 32):
        daily_metrics[d] = {
            'D_RN': 0, 'D_UC': 0, 'D_NT': 0,
            'N_RN': 0, 'N_UC': 0, 'N_NT': 0,
            'is_weekend': False
        }
        
    for shift in db_shifts:
        dt = datetime.strptime(shift.date, "%Y-%m-%d")
        day_num = dt.day
        is_we = dt.weekday() in [5, 6]
        daily_metrics[day_num]['is_weekend'] = is_we
        
        prefix = 'D_' if "7 AM" in shift.time_slot else 'N_'
        for claim in shift.claims:
            if claim.user.title == 'Nurse': daily_metrics[day_num][prefix + 'RN'] += 1
            elif claim.user.title == 'Unit Clerk': daily_metrics[day_num][prefix + 'UC'] += 1
            elif claim.user.title == 'Nurse Tech': daily_metrics[day_num][prefix + 'NT'] += 1

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
                           all_months_list=all_months_list, daily_metrics=daily_metrics)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Check for manager log in via initials entry field
        manager_initials = request.form.get('manager_initials')
        if manager_initials:
            user = User.query.filter_by(initials=manager_initials.strip().upper(), role='Manager').first()
            if user:
                session['user_id'] = user.id
                session['user_name'] = user.name
                session['user_role'] = user.role
                return redirect(url_for('index'))
            flash('Invalid Manager Credentials.', 'error')
            return redirect(url_for('login'))

        # Standard staff dropdown profile selection
        user_id = request.form.get('user_id')
        user = User.query.get(user_id)
        if user and user.role == 'Staff':
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            return redirect(url_for('index'))
        flash('Invalid Profile Selection.', 'error')
        
    day_staff = User.query.filter_by(preferred_shift='Day', role='Staff').order_by(User.name).all()
    night_staff = User.query.filter_by(preferred_shift='Night', role='Staff').order_by(User.name).all()
    
    return render_template('login.html', day_staff=day_staff, night_staff=night_staff)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    shift = Shift.query.get(shift_id)
    if not shift: return redirect(url_for('index'))
        
    month_key = shift.date[:7]
    status_record = MonthStatus.query.filter_by(month_key=month_key).first()
    if status_record and status_record.is_finalized:
        flash('Schedule is locked!', 'error')
        return redirect(url_for('index', month=int(month_key.split('-')[1])))

    dt = datetime.strptime(shift.date, "%Y-%m-%d")
    is_weekend = dt.weekday() in [5, 6]
    max_rn = 6 if is_weekend else 7
    max_uc = 1 if is_weekend else 2

    requesting_user = User.query.get(session['user_id'])
    
    current_rn = sum(1 for c in shift.claims if c.user.title == 'Nurse')
    current_uc = sum(1 for c in shift.claims if c.user.title == 'Unit Clerk')

    if requesting_user.title == 'Nurse' and current_rn >= max_rn:
        flash(f'Cannot sign up! Nurse roster cap ({max_rn}) reached for this day.', 'error')
        return redirect(url_for('index', month=dt.month))
    if requesting_user.title == 'Unit Clerk' and current_uc >= max_uc:
        flash(f'Cannot sign up! Unit Clerk roster cap ({max_uc}) reached for this day.', 'error')
        return redirect(url_for('index', month=dt.month))

    if not ShiftClaim.query.filter_by(shift_id=shift_id, user_id=requesting_user.id).first():
        db.session.add(ShiftClaim(shift_id=shift_id, user_id=requesting_user.id, status='Pending Approval'))
        db.session.commit()
        flash('Sign-up request recorded!', 'success')
        
    return redirect(url_for('index', month=dt.month))

@app.route('/manager/review-claim/<int:claim_id>/<action>')
def review_claim(claim_id, action):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    claim = ShiftClaim.query.get(claim_id)
    current_view_month = datetime.today().month
    if claim:
        current_view_month = int(claim.shift.date.split('-')[1])
        if action == 'approve': claim.status = 'Approved'
        elif action == 'deny': db.session.delete(claim)
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
    if not target_shift: return redirect(url_for('index'))

    if claim_id:
        claim = ShiftClaim.query.get(claim_id)
        if claim:
            claim.shift_id = target_shift.id
            claim.status = 'Approved'
            db.session.commit()
    elif user_id:
        db.session.add(ShiftClaim(shift_id=target_shift.id, user_id=user_id, status='Approved'))
        db.session.commit()

    return redirect(url_for('index', month=int(target_date.split('-')[1])))

@app.route('/manager/finalize/<month_key>/<int:status>')
def finalize_month(month_key, status):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    record = MonthStatus.query.filter_by(month_key=month_key).first()
    if not record:
        record = MonthStatus(month_key=month_key)
        db.session.add(record)
    record.is_finalized = True if status == 1 else False
    db.session.commit()
    return redirect(url_for('index', month=int(month_key.split('-')[1])))

@app.route('/manager/export/paycor/<month_key>')
def export_paycor(month_key):
    if session.get('user_role') != 'Manager': return "Unauthorized", 403
    
    start_date = f"{month_key}-01"
    end_date = f"{month_key}-31"
    
    shifts = Shift.query.filter(Shift.date >= start_date, Shift.date <= end_date).all()
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Employee_ID_Initials', 'Shift_Date', 'Hours_Worked', 'Shift_Type_Code', 'Job_Title'])
    for s in shifts:
        for c in s.claims:
            if c.status == 'Approved':
                shift_code = "DAY" if "7 AM" in s.time_slot else "NIGHT"
                writer.writerow([c.user.initials, s.date, 12.0, shift_code, c.user.title])
                
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=Paycor_Export_{month_key}.csv"
    return response

@app.route('/admin/register', methods=['GET', 'POST'])
def register_staff():
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'register':
            full_name = request.form.get('name').strip()
            initials = request.form.get('initials').strip().upper()
            role = request.form.get('role')
            title = request.form.get('title', 'Nurse')
            preferred_shift = request.form.get('preferred_shift', 'Day')
            if len(initials) == 3 and not User.query.filter_by(initials=initials).first():
                db.session.add(User(name=full_name, initials=initials, role=role, title=title, preferred_shift=preferred_shift))
                db.session.commit()
                
        elif action == 'set_standing':
            user_id = request.form.get('user_id')
            day_of_week = int(request.form.get('day_of_week'))
            time_slot = request.form.get('time_slot')
            
            if not StandingSchedule.query.filter_by(user_id=user_id, day_of_week=day_of_week, time_slot=time_slot).first():
                db.session.add(StandingSchedule(user_id=user_id, day_of_week=day_of_week, time_slot=time_slot))
                db.session.commit()
                flash('Standing schedule rule added successfully!', 'success')

    all_users = User.query.order_by(User.role.desc(), User.name).all()
    standing_schedules = StandingSchedule.query.all()
    return render_template('register.html', users=all_users, standing_schedules=standing_schedules)

@app.route('/manager/apply-standing/<month_key>')
def apply_standing(month_key):
    if session.get('user_role') != 'Manager': return redirect(url_for('index'))
    
    year, month = map(int, month_key.split('-'))
    num_days = calendar.monthrange(year, month)[1]
    standings = StandingSchedule.query.all()
    
    count = 0
    for day in range(1, num_days + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_of_week = dt.weekday()
        
        for rule in standings:
            if rule.day_of_week == day_of_week:
                shift = Shift.query.filter_by(date=date_str, time_slot=rule.time_slot).first()
                if shift:
                    if not ShiftClaim.query.filter_by(shift_id=shift.id, user_id=rule.user_id).first():
                        db.session.add(ShiftClaim(shift_id=shift.id, user_id=rule.user_id, status='Approved'))
                        count += 1
                        
    db.session.commit()
    flash(f'Injected {count} standing set schedule assignments across this month framework!', 'success')
    return redirect(url_for('index', month=month))

@app.route('/seed-database-xyz')
def seed():
    db.create_all()
    if not User.query.filter_by(initials="ADM").first():
        db.session.add(User(name="Head Administrator", initials="ADM", role="Manager", title="Nurse", preferred_shift="Day"))
    year = datetime.today().year
    for m in range(1, 13):
        num_days = calendar.monthrange(year, m)[1]
        for day in range(1, num_days + 1):
            day_str = f"{year}-{m:02d}-{day:02d}"
            if not Shift.query.filter_by(date=day_str, time_slot="7 AM - 7 PM").first():
                db.session.add(Shift(date=day_str, time_slot="7 AM - 7 PM"))
            if not Shift.query.filter_by(date=day_str, time_slot="7 PM - 7 AM").first():
                db.session.add(Shift(date=day_str, time_slot="7 PM - 7 AM"))
    db.session.commit()
    return "Persistent storage structural architecture configured successfully."

with app.app_context(): 
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)