from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os, csv, io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wholesale_simple.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "change-me"

db = SQLAlchemy(app)

# ---------- Models ----------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    cp = db.Column(db.Float, default=0.0)   # Cost Price
    sp = db.Column(db.Float, default=0.0)   # Selling Price
    mrp = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Retailer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(250), nullable=False)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    retailer_id = db.Column(db.Integer, db.ForeignKey('retailer.id'), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    grand_total = db.Column(db.Float, default=0.0)
    total_items = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="pending")   # pending / delivered / deleted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(250))
    cp = db.Column(db.Float, default=0.0)
    sp = db.Column(db.Float, default=0.0)
    mrp = db.Column(db.Float, default=0.0)
    qty = db.Column(db.Integer, default=0)
    item_total = db.Column(db.Float, default=0.0)

# Create DB if not exists (first run)
if not os.path.exists('wholesale_simple.db'):
    with app.app_context():
        db.create_all()
        print("Database created: wholesale_simple.db")

# ---------- Routes ----------
@app.route('/')
def home():
    return render_template('index.html')

# Return lists as JSON
@app.route('/api/products')
def api_products():
    prods = Product.query.order_by(Product.name).all()
    out = []
    for p in prods:
        out.append({
            'id': p.id, 'name': p.name, 'cp': p.cp, 'sp': p.sp, 'mrp': p.mrp, 'stock': p.stock
        })
    return jsonify(out)

@app.route('/api/retailers')
def api_retailers():
    rs = Retailer.query.order_by(Retailer.shop_name).all()
    out = []
    for r in rs:
        out.append({'id': r.id, 'shop_name': r.shop_name, 'address': r.address, 'phone': r.phone})
    return jsonify(out)

# Return active (non-deleted) orders
@app.route('/api/orders')
def api_orders():
    orders = Order.query.filter(Order.status != 'deleted').order_by(Order.date.desc()).all()
    out = []
    for o in orders:
        retailer = Retailer.query.get(o.retailer_id) if o.retailer_id else None
        items = OrderItem.query.filter_by(order_id=o.id).all()
        out.append({
            'id': o.id,
            # FIX: Add 'Z' to ISO format to ensure JS treats it as UTC
            'date': o.date.isoformat() + 'Z', 
            'retailer_id': o.retailer_id,
            'retailer': retailer.shop_name if retailer else None,
            'grand_total': o.grand_total,
            'total_items': o.total_items,
            'status': o.status,
            'items': [{'product_name': it.product_name, 'qty': it.qty, 'sp': it.sp, 'item_total': it.item_total} for it in items]
        })
    return jsonify(out)

# Add product
@app.route('/api/add_product', methods=['POST'])
def api_add_product():
    data = request.json or request.form
    name = data.get('name')
    try:
        cp = float(data.get('cp', 0))
        sp = float(data.get('sp', 0))
        mrp = float(data.get('mrp', 0))
        stock = int(data.get('stock', 0))
    except:
        return jsonify({'ok': False, 'error': 'Invalid numeric values'}), 400
    if not name:
        return jsonify({'ok': False, 'error': 'Name required'}), 400
    p = Product(name=name, cp=cp, sp=sp, mrp=mrp, stock=stock)
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok': True, 'product': {'id': p.id, 'name': p.name}})


# Update stock and details for an existing product
@app.route('/api/update_product_stock', methods=['POST'])
def api_update_product_stock():
    data = request.json
    try:
        product_id = int(data.get('id'))
        stock_to_add = int(data.get('stock_to_add', 0))
        
        # Prices are updated regardless of stock change
        new_cp = float(data.get('cp', 0))
        new_sp = float(data.get('sp', 0))
        new_mrp = float(data.get('mrp', 0))

    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Invalid ID, stock, or price data provided.'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'ok': False, 'error': f'Product ID {product_id} not found.'}), 404
    
    # Update price fields
    product.cp = new_cp
    product.sp = new_sp
    product.mrp = new_mrp
    
    # Update stock (add the new quantity)
    if stock_to_add > 0:
        product.stock += stock_to_add
    
    db.session.commit()
    return jsonify({'ok': True, 'new_stock': product.stock})


# Add retailer
@app.route('/api/add_retailer', methods=['POST'])
def api_add_retailer():
    data = request.json or request.form
    shop_name = data.get('shop_name')
    address = data.get('address', '')
    phone = data.get('phone', '')
    if not shop_name:
        return jsonify({'ok': False, 'error': 'Shop name required'}), 400
    r = Retailer(shop_name=shop_name, address=address, phone=phone)
    db.session.add(r)
    db.session.commit()
    return jsonify({'ok': True, 'retailer': {'id': r.id, 'shop_name': r.shop_name}})

# Place order (transaction-like)
@app.route('/api/place_order', methods=['POST'])
def api_place_order():
    data = request.json
    if not data or 'items' not in data or not isinstance(data['items'], list):
        return jsonify({'ok': False, 'error': 'Items required'}), 400

    # FIX: Mandate retailer selection (Backend validation)
    retailer_id_str = data.get('retailer_id') 
    if not retailer_id_str or str(retailer_id_str).strip() == "":
        return jsonify({'ok': False, 'error': 'Retailer selection is required.'}), 400

    try:
        retailer_id = int(retailer_id_str)
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid retailer ID format.'}), 400
        
    items_payload = data['items']  # list of {product_id, qty}
    # Validate and compute totals
    grand_total = 0.0
    total_items = 0
    prods = {}
    for it in items_payload:
        try:
            pid = int(it.get('product_id'))
            qty = int(it.get('qty', 0))
        except:
            return jsonify({'ok': False, 'error': 'Invalid item data'}), 400
        if qty <= 0:
            return jsonify({'ok': False, 'error': f'Invalid qty for product {pid}'}), 400
        p = Product.query.get(pid)
        if not p:
            return jsonify({'ok': False, 'error': f'Product id {pid} not found'}), 404
        if p.stock < qty:
            return jsonify({'ok': False, 'error': f'Insufficient stock for {p.name} (available {p.stock})'}), 409
        prods[pid] = (p, qty)
        grand_total += p.sp * qty
        total_items += qty
    # All clear — create order and decrement stocks
    order = Order(retailer_id=retailer_id, grand_total=grand_total, total_items=total_items)
    db.session.add(order)
    db.session.flush()  # get order.id
    for pid, (p, qty) in prods.items():
        p.stock -= qty
        oi = OrderItem(order_id=order.id, product_id=p.id, product_name=p.name,
                       cp=p.cp, sp=p.sp, mrp=p.mrp, qty=qty, item_total=p.sp*qty)
        db.session.add(oi)
    db.session.commit()
    return jsonify({'ok': True, 'order_id': order.id})

# --- Retailer detail + retailer orders endpoints (skip deleted) ---
@app.route('/api/retailer/<int:rid>')
def api_retailer_detail(rid):
    r = Retailer.query.get(rid)
    if not r:
        return jsonify({'ok': False, 'error': 'Retailer not found'}), 404
    return jsonify({
        'ok': True,
        'retailer': {'id': r.id, 'shop_name': r.shop_name, 'address': r.address, 'phone': r.phone}
    })

@app.route('/api/retailer_orders/<int:rid>')
def api_retailer_orders(rid):
    orders = Order.query.filter_by(retailer_id=rid).filter(Order.status != 'deleted').order_by(Order.date.desc()).all()
    out = []
    for o in orders:
        items = OrderItem.query.filter_by(order_id=o.id).all()
        out.append({
            'id': o.id,
            # FIX: Add 'Z' to ISO format to ensure JS treats it as UTC
            'date': o.date.isoformat() + 'Z', 
            'grand_total': o.grand_total,
            'total_items': o.total_items,
            'status': o.status,
            'items': [{'product_name': it.product_name, 'qty': it.qty, 'sp': it.sp, 'item_total': it.item_total} for it in items]
        })
    return jsonify({'ok': True, 'orders': out})

# Delete order (restore stock, mark deleted)
@app.route('/api/delete_order/<int:oid>', methods=['POST'])
def delete_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'ok': False, 'error': 'Order not found'}), 404
    if order.status == "deleted":
        return jsonify({'ok': False, 'error': 'Already deleted'}), 400
    # restore stock
    items = OrderItem.query.filter_by(order_id=oid).all()
    for it in items:
        p = Product.query.get(it.product_id)
        if p:
            p.stock += it.qty
    order.status = "deleted"
    db.session.commit()
    return jsonify({'ok': True})

# Mark delivered
@app.route('/api/deliver_order/<int:oid>', methods=['POST'])
def deliver_order(oid):
    order = Order.query.get(oid)
    if not order:
        return jsonify({'ok': False, 'error': 'Order not found'}), 404
    if order.status == "deleted":
        return jsonify({'ok': False, 'error': 'Order already deleted'}), 400
    order.status = "delivered"
    db.session.commit()
    return jsonify({'ok': True})

# Export CSV (optional)
@app.route('/export')
def export_csv():
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['order_id','date','retailer','product','qty','sp','cp','item_total','grand_total','status'])
    orders = Order.query.order_by(Order.date.desc()).all()
    for o in orders:
        retailer = Retailer.query.get(o.retailer_id)
        items = OrderItem.query.filter_by(order_id=o.id).all()
        for it in items:
            cw.writerow([o.id, o.date.isoformat(), retailer.shop_name if retailer else '', it.product_name, it.qty, it.sp, it.cp, it.item_total, o.grand_total, o.status])
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    filename = f'backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True)
