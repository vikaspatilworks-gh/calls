from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client
from functools import wraps
from datetime import datetime, date
import os
from supabase import create_client, Client

# Replace with your actual credentials:
REAL_URL = "https://mxaphksqgwmjtndboiqf.supabase.co"
REAL_KEY = "sb_publishable_wuvUKqh_ExzFcRWv3GxbyA_RLwYTZO_"

SUPABASE_URL = os.environ.get("SUPABASE_URL") or REAL_URL
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or REAL_KEY

# Ensure it is not empty before creating client
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must not be empty.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- Authentication Decorators ---
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
            return jsonify({'success': False, 'error': 'Unauthorized: Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


# --- Login / Logout Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd = request.form.get('password', '').strip()

        # 1. Master Fallback Admin Check
        if uname == 'admin' and pwd == 'admin@123':
            session['user'] = 'admin'
            session['display_name'] = 'Master Admin'
            session['role'] = 'admin'
            session['staff_id'] = None
            return redirect(url_for('dashboard'))

        # 2. Check Database Staff Table
        try:
            res = supabase.table('staff').select('*').eq('username', uname).eq('password', pwd).execute()
            if res.data and len(res.data) > 0:
                staff_user = res.data[0]
                session['user'] = staff_user.get('username')
                session['display_name'] = staff_user.get('staffname', staff_user.get('username'))
                session['role'] = staff_user.get('role', 'staff')
                session['staff_id'] = staff_user.get('staff_id')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid Username or Password', 'danger')
        except Exception as e:
            flash(f'Database error: {str(e)}', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# --- Main Dashboard ---
@app.route('/')
@login_required
def dashboard():
    try:
        # Fetch lookups & staff list
        lookups = supabase.table('app_lookups').select('*').eq('is_active', True).execute().data
        staff_list = supabase.table('staff').select('*').execute().data
        customers = supabase.table('customers').select('*').execute().data

        # Fetch all calls
        all_calls = supabase.table('calls').select('*').order('created_at', desc=True).execute().data

        # Map customer details into a lookup dictionary
        cust_map = {c['cust_id']: c for c in customers}

        # Filter calls:
        # 1. Include ALL Pending, Running, Other (even old ones)
        # 2. Include Completed calls ONLY if created today
        today_str = date.today().isoformat()
        
        filtered_calls = []
        for call in all_calls:
            status = (call.get('call_status') or 'Pending').strip().capitalize()
            created_at_raw = call.get('created_at', '')
            call_date = created_at_raw[:10] if created_at_raw else ''

            is_pending_running = status in ['Pending', 'Running', 'Other']
            is_completed_today = (status == 'Complete' or status == 'Completed') and (call_date == today_str)

            if is_pending_running or is_completed_today:
                c_info = cust_map.get(call.get('cust_id'), {})
                call['customer_name'] = c_info.get('customer', 'N/A')
                call['address'] = c_info.get('address', '-')
                call['cust_mobile'] = c_info.get('mobile', '-')
                call['status_clean'] = status
                filtered_calls.append(call)

        # Group filtered calls by staff member
        staff_call_groups = []
        
        # Build grouped list for each registered staff member
        for st in staff_list:
            s_id = st.get('staff_id')
            assigned_calls = [c for c in filtered_calls if c.get('allot_staff_id') == s_id]
            staff_call_groups.append({
                'staff_id': s_id,
                'staffname': st.get('staffname', 'Unknown Staff'),
                'mobile': st.get('mobile', '-'),
                'calls': assigned_calls
            })

        # Include unassigned calls category if any exist
        unassigned_calls = [c for c in filtered_calls if not c.get('allot_staff_id')]
        if unassigned_calls:
            staff_call_groups.append({
                'staff_id': 0,
                'staffname': 'Unassigned / Open Pool',
                'mobile': '-',
                'calls': unassigned_calls
            })

        return render_template(
            'index.html',
            staff_groups=staff_call_groups,
            staff_list=staff_list,
            customers=customers,
            lookups=lookups,
            current_user=session
        )
    except Exception as e:
        return f"System Error: {str(e)}", 500


# --- Unified Search / Fetch Endpoint for Editing ---
@app.route('/api/search/<entity_type>')
@login_required
def search_entity(entity_type):
    term = request.args.get('term', '').strip()
    try:
        if entity_type == 'customer':
            query = supabase.table('customers').select('*')
            if term:
                query = query.ilike('customer', f'%{term}%')
            data = query.limit(20).execute().data
            return jsonify({'success': True, 'data': data})

        elif entity_type == 'staff':
            if session.get('role') != 'admin':
                return jsonify({'success': False, 'error': 'Admin permission required'}), 403
            query = supabase.table('staff').select('*')
            if term:
                query = query.ilike('staffname', f'%{term}%')
            data = query.limit(20).execute().data
            return jsonify({'success': True, 'data': data})

        elif entity_type == 'call':
            query = supabase.table('calls').select('*')
            if term:
                query = query.ilike('complaint', f'%{term}%')
            data = query.order('created_at', desc=True).limit(20).execute().data
            return jsonify({'success': True, 'data': data})

        return jsonify({'success': False, 'error': 'Invalid entity type'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Save / Update Endpoints ---
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


@app.route('/api/save-call', methods=['POST'])
@login_required
def save_call():
    try:
        data = request.json
        call_id = data.get('call_id')
        payload = {
            'cust_id': data.get('cust_id'),
            'allot_staff_id': data.get('allot_staff_id') if data.get('allot_staff_id') else None,
            'complaint': data.get('complaint'),
            'call_status': data.get('call_status', 'Pending')
        }
        if call_id:
            supabase.table('calls').update(payload).eq('call_id', call_id).execute()
        else:
            supabase.table('calls').insert(payload).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/update-status-inline', methods=['POST'])
@login_required
def update_status_inline():
    try:
        data = request.json
        call_id = data.get('call_id')
        status = data.get('call_status')
        supabase.table('calls').update({'call_status': status}).eq('call_id', call_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
