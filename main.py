from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client
from functools import wraps
from datetime import datetime, date
import configparser
import os

# --- 1. Load Config from serverconfig.ini ---
config = configparser.ConfigParser()
config_file_path = os.path.join(os.path.dirname(__file__), 'serverconfig.ini')

if os.path.exists(config_file_path):
    config.read(config_file_path)
    SUPABASE_URL = config.get('SUPABASE', 'SUPABASE_URL', fallback=os.environ.get('SUPABASE_URL'))
    SUPABASE_KEY = config.get('SUPABASE', 'SUPABASE_KEY', fallback=os.environ.get('SUPABASE_KEY'))
    SECRET_KEY = config.get('FLASK', 'SECRET_KEY', fallback='dev-secret-key')
else:
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')

app = Flask(__name__)
app.secret_key = SECRET_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- 2. Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin authorization required'}), 403
        return f(*args, **kwargs)
    return decorated_function


# --- 3. Login / Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd = request.form.get('password', '').strip()

        # Fallback Master Admin
        if uname == 'admin' and pwd == 'admin@123':
            session['user'] = 'admin'
            session['display_name'] = 'Master Admin'
            session['role'] = 'admin'
            session['staff_id'] = 0
            return redirect(url_for('dashboard'))

        # Query Database
        try:
            res = supabase.table('staff').select('*').eq('username', uname).eq('password', pwd).execute()
            if res.data and len(res.data) > 0:
                user_info = res.data[0]
                session['user'] = user_info.get('username')
                session['display_name'] = user_info.get('staffname', user_info.get('username'))
                session['role'] = user_info.get('role', 'staff')
                session['staff_id'] = user_info.get('staff_id')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid Username or Password', 'danger')
        except Exception as e:
            flash(f'Database Connection Error: {str(e)}', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# --- 4. Main Dashboard ---
@app.route('/')
@login_required
def dashboard():
    try:
        lookups = supabase.table('app_lookups').select('*').eq('is_active', True).execute().data
        staff_list = supabase.table('staff').select('*').execute().data
        customers = supabase.table('customers').select('*').execute().data
        all_calls = supabase.table('calls').select('*').order('created_at', desc=True).execute().data

        cust_map = {c['cust_id']: c for c in customers}
        staff_map = {s['staff_id']: s for s in staff_list}
        today_str = date.today().isoformat()

        # Process Calls
        active_calls = []
        today_completed_calls = []

        for call in all_calls:
            status = (call.get('call_status') or 'Pending').strip().capitalize()
            created_at_raw = str(call.get('call_date') or call.get('created_at') or '')
            call_date_str = created_at_raw[:10]

            c_info = cust_map.get(call.get('cust_id'), {})
            call['customer_name'] = c_info.get('customer', 'Unknown')
            call['address'] = c_info.get('address', '-')
            call['cust_mobile'] = c_info.get('mobile', '-')
            call['status_clean'] = status
            
            # Format assigned staff
            assigned_staff_id = call.get('allot_staff_id')
            call['assigned_staff_name'] = staff_map.get(assigned_staff_id, {}).get('staffname', 'Unassigned')

            if status in ['Complete', 'Completed']:
                if call_date_str == today_str:
                    today_completed_calls.append(call)
            else:
                active_calls.append(call)

        # 1. Staff Queues
        staff_groups = []
        for st in staff_list:
            s_id = st.get('staff_id')
            s_active = [c for c in active_calls if c.get('allot_staff_id') == s_id]
            s_completed_today = [c for c in today_completed_calls if c.get('allot_staff_id') == s_id]
            staff_groups.append({
                'staff_id': s_id,
                'staffname': st.get('staffname', 'Staff'),
                'mobile': st.get('mobile', '-'),
                'active_calls': s_active,
                'completed_count': len(s_completed_today),
                'completed_calls': s_completed_today
            })

        # 2. Unassigned Open Calls
        unassigned_open = [c for c in active_calls if not c.get('allot_staff_id') and not c.get('is_admin_queue')]
        unassigned_open_completed = [c for c in today_completed_calls if not c.get('allot_staff_id') and not c.get('is_admin_queue')]

        # 3. Unassigned Admin Calls
        unassigned_admin = [c for c in active_calls if not c.get('allot_staff_id') and c.get('is_admin_queue')]
        unassigned_admin_completed = [c for c in today_completed_calls if not c.get('allot_staff_id') and c.get('is_admin_queue')]

        now = datetime.now()
        current_time_info = {
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M')
        }

        return render_template(
            'index.html',
            staff_groups=staff_groups,
            unassigned_open={'calls': unassigned_open, 'completed_count': len(unassigned_open_completed), 'completed_calls': unassigned_open_completed},
            unassigned_admin={'calls': unassigned_admin, 'completed_count': len(unassigned_admin_completed), 'completed_calls': unassigned_admin_completed},
            staff_list=staff_list,
            customers=customers,
            lookups=lookups,
            current_time_info=current_time_info,
            current_user=session
        )
    except Exception as e:
        return f"System Dashboard Error: {str(e)}", 500


# --- 5. Generic Master Fetch API ---
@app.route('/api/master-data/<entity_type>')
@login_required
def master_data(entity_type):
    try:
        if entity_type == 'customer':
            data = supabase.table('customers').select('*').order('created_at', desc=True).execute().data
        elif entity_type == 'staff':
            data = supabase.table('staff').select('staff_id, staffname, mobile, username, role').execute().data
        elif entity_type == 'call':
            data = supabase.table('calls').select('*').order('created_at', desc=True).limit(100).execute().data
        else:
            return jsonify({'success': False, 'error': 'Invalid entity'}), 400
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- 6. Save & Update APIs ---
@app.route('/api/save-call', methods=['POST'])
@login_required
def save_call():
    try:
        data = request.json
        call_id = data.get('call_id')
        
        allot_staff_val = data.get('allot_staff_id')
        allot_staff_id = int(allot_staff_val) if allot_staff_val and str(allot_staff_val).isdigit() and int(allot_staff_val) > 0 else None

        payload = {
            'call_date': data.get('call_date') or date.today().isoformat(),
            'call_time': data.get('call_time') or datetime.now().strftime('%H:%M:%S'),
            'call_staff_id': session.get('staff_id'),
            'call_staff_name': session.get('display_name'),
            'cust_id': int(data.get('cust_id')) if data.get('cust_id') else None,
            'call_type': data.get('call_type'),
            'call_subtype': data.get('call_subtype'),
            'complaint': data.get('complaint'),
            'callback_number': data.get('callback_number'),
            'allot_staff_id': allot_staff_id,
            'is_admin_queue': True if data.get('queue_type') == 'admin' else False,
            'call_status': data.get('call_status', 'Pending')
        }

        if call_id:
            supabase.table('calls').update(payload).eq('call_id', call_id).execute()
        else:
            supabase.table('calls').insert(payload).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-customer', methods=['POST'])
@login_required
def save_customer():
    try:
        data = request.json
        cust_id = data.get('cust_id')
        payload = {
            'customer': data.get('customer'),
            'mobile': data.get('mobile'),
            'address': data.get('address'),
            'contact_person': data.get('contact_person'),
            'email': data.get('email'),
            'city': data.get('city'),
            'cust_type': data.get('cust_type', 'Live')
        }
        if cust_id:
            supabase.table('customers').update(payload).eq('cust_id', cust_id).execute()
        else:
            supabase.table('customers').insert(payload).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-staff', methods=['POST'])
@admin_required
def save_staff():
    try:
        data = request.json
        staff_id = data.get('staff_id')
        payload = {
            'staffname': data.get('staffname'),
            'mobile': data.get('mobile'),
            'username': data.get('username'),
            'password': data.get('password'),
            'role': data.get('role', 'staff')
        }
        if staff_id:
            supabase.table('staff').update(payload).eq('staff_id', staff_id).execute()
        else:
            supabase.table('staff').insert(payload).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/quick-status', methods=['POST'])
@login_required
def quick_status():
    try:
        data = request.json
        supabase.table('calls').update({'call_status': data.get('call_status')}).eq('call_id', data.get('call_id')).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
