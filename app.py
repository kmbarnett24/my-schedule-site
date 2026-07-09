from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'super-secure-key-123'

# Internal database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///schedule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Structure
class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(20), nullable=False) # e.g., Monday
    shift_type = db.Column(db.String(10), nullable=False)  # Day or Night
    time_slot = db.Column(db.String(50), nullable=False)   # e.g., 7:00 AM - 7:00 PM
    claimed_by = db.Column(db.String(100), default=None, nullable=True)
    status = db.Column(db.String(20), default='Open')      # Open, Pending, Approved

# Main Public Page (Anyone with the link can see this)
@app.route('/')
def index():
    db.create_all()
    
    # Automatically generate an organized weekly template if empty
    if Shift.query.count() == 0:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        sample_shifts = []
        for day in days:
            sample_shifts.append(Shift(day_of_week=day, shift_type='Day', time_slot='7:00 AM - 7:00 PM'))
            sample_shifts.append(Shift(day_of_week=day, shift_type='Night', time_slot='7:00 PM - 7:00 AM'))
        db.session.add_all(sample_shifts)
        db.session.commit()

    day_shifts = Shift.query.filter_by(shift_type='Day').all()
    night_shifts = Shift.query.filter_by(shift_type='Night').all()
    return render_template('index.html', day_shifts=day_shifts, night_shifts=night_shifts)

# Staff Submit Request Route
@app.route('/claim/<int:shift_id>', methods=['POST'])
def claim_shift(shift_id):
    staff_name = request.form.get('staff_name')
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Open':
        shift.claimed_by = staff_name
        shift.status = 'Pending Approval'
        db.session.commit()
        flash(f'Successfully requested the {shift.day_of_week} {shift.shift_type} shift!', 'success')
    return redirect(url_for('index'))

# Secret Manager Dashboard Area 
# (You can access this by adding /manager to the end of your link)
@app.route('/manager')
def manager_dashboard():
    shifts = Shift.query.all()
    return render_template('manager.html', shifts=shifts)

@app.route('/manager/review/<int:shift_id>/<action>')
def review_shift(shift_id, action):
    shift = Shift.query.get(shift_id)
    if shift and shift.status == 'Pending Approval':
        if action == 'approve':
            shift.status = 'Approved'
            flash('Shift enrollment finalized!', 'success')
        elif action == 'deny':
            shift.status = 'Open'
            shift.claimed_by = None
            flash('Shift request rejected and opened back up.', 'info')
        db.session.commit()
    return redirect(url_for('manager_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)