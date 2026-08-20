from flask import Flask, render_template, request, redirect, url_for, jsonify
from supabase import create_client, Client
import os

app = Flask(__name__)

# --- Supabase Credentials ---
# Reads from Render Environment Variables first, falls back to static string if provided
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://your-supabase-url.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "your-supabase-anon-key")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# 1. Main Dashboard Route
@app.route('/')
def dashboard():
    try:
        # Fetch active lookup options (Complaint types, statuses, customer types, etc.)
        lookups = supabase.table('app_lookups').select('*').eq('is_active', True).execute().data
        
        # Fetch staff list
        staff_list = supabase.table('staff').select('staff_id, staffname').execute().data
        
        # Fetch customer list
        customer_list = supabase.table('customers').select('cust_id, customer, mobile, cust_type').execute().data
        
        # Fetch recent calls with customer details and assigned staff
        recent_calls = supabase.table('calls').select(
            'call_id, complaint, call_status, created_at, allot_staff_id, cust_id, customers(customer, mobile), staff(staffname)'
        ).order('created_at', desc=True).limit(50).execute().data
        
        return render_template(
            'index.html',
            lookups=lookups,
            staff=staff_list,
            customers=customer_list,
            calls=recent_calls
        )
    except Exception as e:
        return f"Database error: {str(e)}", 500


# 2. Staff Cards Route
@app.route('/staff-cards')
def staff_cards():
    try:
        # 1. Fetch lookups & staff list
        lookups = supabase.table('app_lookups').select('*').eq('is_active', True).execute().data
        staff_list = supabase.table('staff').select('staff_id, staffname').execute().data
        
        # 2. Fetch calls and customers separately to avoid PostgREST join lookup crashes
        calls_data = supabase.table('calls').select('*').order('created_at', desc=True).execute().data
        customers_data = supabase.table('customers').select('cust_id, customer, mobile').execute().data

        # Map customer info into a fast lookup dictionary
        cust_map = {c['cust_id']: c for c in customers_data}

        # Merge customer details into each call dictionary
        for call in calls_data:
            c_info = cust_map.get(call.get('cust_id'), {})
            call['customer_name'] = c_info.get('customer', 'Unknown')
            call['mobile'] = c_info.get('mobile', '')

        return render_template(
            'staff_cards.html',
            staff=staff_list,
            calls=calls_data,
            lookups=lookups
        )
    except Exception as e:
        return f"Database error in staff cards: {str(e)}", 500


# 3. Add Customer API / Form Action
@app.route('/add-customer', methods=['POST'])
def add_customer():
    try:
        data = request.form
        customer_name = data.get('customer')
        mobile = data.get('mobile')
        cust_type = data.get('cust_type', 'Live')

        supabase.table('customers').insert({
            'customer': customer_name,
            'mobile': mobile,
            'cust_type': cust_type
        }).execute()

        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Error adding customer: {str(e)}", 400


# 4. Log Complaint API / Form Action
@app.route('/log-call', methods=['POST'])
def log_call():
    try:
        data = request.form
        cust_id = data.get('cust_id')
        complaint = data.get('complaint')
        allot_staff_id = data.get('allot_staff_id')
        call_status = data.get('call_status', 'Pending')

        supabase.table('calls').insert({
            'cust_id': cust_id,
            'complaint': complaint,
            'allot_staff_id': allot_staff_id,
            'call_status': call_status
        }).execute()

        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Error logging call: {str(e)}", 400


# 5. AJAX Endpoint to Update Call Status from Staff Cards or Dashboard
@app.route('/update-status', methods=['POST'])
def update_status():
    try:
        payload = request.get_json()
        call_id = payload.get('call_id')
        new_status = payload.get('call_status')

        supabase.table('calls').update({
            'call_status': new_status
        }).eq('call_id', call_id).execute()

        return jsonify({'success': True, 'message': 'Status updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
