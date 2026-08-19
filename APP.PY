import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Replace with your actual Supabase credentials
SUPABASE_URL = "https://mxaphksqgwmjtndboiqf.supabase.co"
SUPABASE_KEY = "sb_publishable_wuvUKqh_ExzFcRWv3GxbyA_RLwYTZO_"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def dashboard():
    lookups = supabase.table('app_lookups').select('*').eq('is_active', True).execute().data
    staff_list = supabase.table('staff').select('staff_id, staffname').execute().data
    customers = supabase.table('customers').select('cust_id, customer, cust_type, mobile').execute().data
    recent_calls = supabase.table('calls').select(
        '*, customers!fk_calls_customer(customer), staff!fk_calls_allot_staff(staffname)'
    ).order('created_at', desc=True).limit(10).execute().data
    
    return render_template('index.html', lookups=lookups, staff=staff_list, customers=customers, calls=recent_calls)

@app.route('/customers/save', methods=['POST'])
def save_customer():
    data = {
        "customer": request.form.get('customer'),
        "cust_type": request.form.get('cust_type'),
        "software": request.form.get('software'),
        "mobile": request.form.get('mobile'),
        "city": request.form.get('city'),
        "area": request.form.get('area'),
        "market": request.form.get('market'),
        "gstin": request.form.get('gstin'),
        "total_pc": int(request.form.get('total_pc') or 0),
        "amc_amt": float(request.form.get('amc_amt') or 0)
    }
    supabase.table('customers').insert(data).execute()
    return redirect(url_for('dashboard'))

@app.route('/calls/save', methods=['POST'])
def save_call():
    data = {
        "call_no": f"CALL-{os.urandom(2).hex().upper()}",
        "cust_id": int(request.form.get('cust_id')),
        "allot_staff": int(request.form.get('allot_staff')) if request.form.get('allot_staff') else None,
        "call_type": request.form.get('call_type'),
        "call_mode": request.form.get('call_mode'),
        "call_details": request.form.get('call_details'),
        "call_contact": request.form.get('call_contact'),
        "call_date": request.form.get('call_date')
    }
    supabase.table('calls').insert(data).execute()
    return redirect(url_for('dashboard'))

@app.route('/settings/lookup/save', methods=['POST'])
def save_lookup():
    category = request.form.get('category')
    item_value = request.form.get('item_value')
    supabase.table('app_lookups').insert({'category': category, 'item_value': item_value}).execute()
    return redirect(url_for('dashboard'))

@app.route('/api/call-metrics')
def call_metrics():
    calls = supabase.table('calls').select('call_type').execute().data
    type_counts = {}
    for c in calls:
        t = c.get('call_type') or 'Unspecified'
        type_counts[t] = type_counts.get(t, 0) + 1
    return jsonify(type_counts)

if __name__ == '__main__':
    app.run(debug=True)
