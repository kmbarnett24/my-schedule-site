from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super-secure-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calendar_schedule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Architecture
class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(20), nullable=False) # YYYY-MM-DD
    month_name = db.Column(db.String(20), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    shift_type = db.Column(db.String(10), nullable=False) # Day or Night
    time_slot = db.Column(db.String(30), nullable=False)  # 07:00 - 19:00 or 19:00 - 07:00
    claimed_by = db.Column(db.String(100), default=None, nullable=True)
    requested_off = db.Column(db.String(200), default="", nullable=True) # Holds comma-separated names with "R"
    status = db.Column(db.String(20), default='Open')     # Open, Pending, Approved

@app.route('/')
def index():
    db.create_all()
    
    # Auto-generate 2026 calendar baseline on launch if empty
    if Shift.query.count() == 0:
        current_year = 2026
        start_date = datetime(current_year, 1, 1)
        end_date = datetime(current_year, 12, 31)
        delta = end_date - start_date
        
        all_shifts = []
        for i in range(delta.days + 1):
            day_ctx = start_date + timedelta(days=i)
            d_str = day_ctx.strftime('%Y-%m-%d')
            m_name = day_ctx.strftime('%B')
            d_num = day_ctx.day
            
            # Setup Day Matrix
            all_shifts.append(Shift(date_str=d_str, month_name=m_name, day_number=d_num, shift_type='Day', time_slot='07:00 - 19:00'))
            # Setup Night Matrix
            all_shifts.append(Shift(date_str=d_str, month_name=m_name, day_number=d_num, shift_type='Night', time_slot='19:00 - 07:00'))
            
        db.session.add_all(all_shifts)
        db.session.commit()

    # Get active filter month (default to current calendar month)
    selected_month = request.args.get('month', datetime.now().strftime('%B'))
    
    # Package shifts nicely for calendar UI
    shifts_in_month = Shift.query.filter_by(month_name=selected_month).order_by(Shift.day_number).all()
    
    # Structure days: { day_number: { 'Day': shift_obj, 'Night': shift_obj } }
    calendar_days = {}
    for s in shifts_in_month:
        if s.day_number not in calendar_days:
            calendar_days[s.day_number] = {}
        calendar_days[s.day_number][s.shift_type] = s

    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return render_template('index.html', calendar_days=calendar_days, current_month=selected_month, months=months)

# Staff Claim Action
@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    staff_name = request.form.get('staff_name').strip()
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open' and staff_name:
        shift.claimed_by = staff_name
        shift.status = 'Pending'
        db.session.commit()
        flash(f'Requested {shift.shift_type} shift on day {shift.day_number}!', 'success')
    return redirect(url_for('index', month=shift.month_name))

# Staff Add "R" Appointment Restriction Action
@app.route('/request-off/<int:shift_id>', methods=['POST'])
def request_off(shift_id):
    staff_name = request.form.get('staff_name').strip()
    shift = Shift.query.get(shift_id)
    if shift and staff_name:
        current_list = [name.strip() for name in shift.requested_off.split(',') if name.strip()]
        if staff_name not in current_list:
            current_list.append(staff_name)
            shift.requested_off = ", ".join(current_list)
            db.session.commit()
            flash(f'Marked "R" for {staff_name} on {shift.date_str} ({shift.shift_type})!', 'info')
    return redirect(url_for('index', month=shift.month_name))

# Manager Portal
@app.route('/manager')
def manager_dashboard():
    selected_month = request.args.get('month', datetime.now().strftime('%B'))
    pending_shifts = Shift.query.filter_by(status='Pending', month_name=selected_month).all()
    all_shifts = Shift.query.filter_by(month_name=selected_month).order_by(Shift.day_number).all()
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return render_template('manager.html', pending_shifts=pending_shifts, all_shifts=all_shifts, current_month=selected_month, months=months)

@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    shift = Shift.query.get(shift_id)
    if shift:
        if action == 'approve':
            shift.status = 'Approved'
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by = None
        db.session.commit()
    return redirect(url_for('manager_dashboard', month=shift.month_name))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)