from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import or_
import pytz

app = Flask(__name__)
app.secret_key = 'greengrocer-secret-2025'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///greengrocer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Set Indian Timezone
IST = pytz.timezone('Asia/Kolkata')

def get_ist_time():
    """Return current time in Indian Standard Time"""
    return datetime.now(IST)

# ===================== MODELS =====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    
    def __repr__(self):
        return f'<Product {self.name}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=get_ist_time)
    total = db.Column(db.Float, nullable=False)
    items = db.Column(db.JSON)
    
    def __repr__(self):
        return f'<Transaction {self.id} - ₹{self.total}>'

# ===================== LOGIN CHECK =====================
@app.before_request
def require_login():
    allowed = ['login', 'register', 'static']
    if request.endpoint not in allowed and 'logged_in' not in session:
        return redirect(url_for('login'))
    

# ===================== REGISTER =====================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))

        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()

        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# ===================== LOGIN =====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(
            username=request.form['username'],
            password=request.form['password']
        ).first()

        if user:
            session['logged_in'] = True
            session['user'] = user.username
            flash(f'Welcome {user.username}! 👋', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')

    return render_template('login.html')

# ===================== LOGOUT =====================
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

# ===================== DASHBOARD =====================
# ===================== DASHBOARD =====================
@app.route('/')
@app.route('/dashboard')
def dashboard():
    try:
        total_products = Product.query.count()
        total_sales = db.session.query(db.func.sum(Transaction.total)).scalar() or 0
        recent = Transaction.query.order_by(Transaction.date.desc()).limit(5).all()
        
        # Get current IST time
        current_time = get_ist_time()
        
        return render_template('dashboard.html',
            total_products=total_products,
            total_sales=round(total_sales, 2),
            recent=recent,
            ist_time=current_time.strftime('%d %b %Y %I:%M %p')
        )
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return render_template('dashboard.html',
            total_products=0,
            total_sales=0,
            recent=[],
            ist_time=get_ist_time().strftime('%d %b %Y %I:%M %p')
        )

# ===================== PRODUCTS MANAGEMENT =====================
@app.route('/products')
def products():
    """Display all products for management"""
    products = Product.query.order_by(Product.name).all()
    return render_template('products.html', products=products)

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    """Add new product page"""
    if request.method == 'POST':
        product = Product(
            name=request.form['name'],
            category=request.form['category'],
            price=float(request.form['price']),
            stock=int(request.form['stock'])
        )
        db.session.add(product)
        db.session.commit()
        flash(f'Product "{product.name}" added successfully!', 'success')
        return redirect(url_for('products'))
    
    return render_template('add_product.html')

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    """Edit product page"""
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        product.name = request.form['name']
        product.category = request.form['category']
        product.price = float(request.form['price'])
        product.stock = int(request.form['stock'])
        
        db.session.commit()
        flash(f'Product "{product.name}" updated successfully!', 'success')
        return redirect(url_for('products'))
    
    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:id>', methods=['POST'])
def delete_product(id):
    """Delete product"""
    product = Product.query.get_or_404(id)
    product_name = product.name
    
    db.session.delete(product)
    db.session.commit()
    
    flash(f'Product "{product_name}" deleted successfully!', 'info')
    return redirect(url_for('products'))

# ===================== POS (POINT OF SALE) =====================
@app.route('/pos', methods=['GET'])
def pos():
    """Point of Sale page - Display products and handle cart"""
    # Get search query
    search = request.args.get('search', '')
    
    # Query products based on search
    if search:
        products = Product.query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.category.ilike(f'%{search}%')
            )
        ).order_by(Product.name).all()
    else:
        products = Product.query.order_by(Product.name).all()
    
    return render_template('pos.html', products=products)


# ===================== CHECKOUT =====================
@app.route('/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        cart = data.get('cart', [])
        payment_method = data.get('payment_method', 'cash')

        if not cart:
            return jsonify({'success': False, 'message': 'Cart is empty'})

        total = 0
        items_list = []
        transaction_items = []

        # Process each item in cart
        for item in cart:
            product = db.session.get(Product, item['id'])

            if not product:
                return jsonify({'success': False, 'message': f'Product not found'})

            if product.stock < item['qty']:
                return jsonify({
                    'success': False, 
                    'message': f'Not enough stock for {product.name}. Available: {product.stock}'
                })

            subtotal = product.price * item['qty']
            total += subtotal

            # Record item for transaction
            transaction_items.append({
                'id': product.id,
                'name': product.name,
                'qty': item['qty'],
                'price': product.price,
                'subtotal': subtotal
            })

            # Update stock
            product.stock -= item['qty']

        # Add GST (5%)
        gst = total * 0.05
        grand_total = total + gst

        # Create transaction record with payment info
        transaction = Transaction(
            total=grand_total,
            items={
                'items': transaction_items,
                'subtotal': total,
                'gst': gst,
                'payment_method': payment_method,
                'date': get_ist_time().strftime('%d %b %Y %I:%M %p')
            }
        )
        db.session.add(transaction)
        db.session.commit()

        response_data = {
            'success': True, 
            'message': f'Sale completed successfully! Total: ₹{grand_total:.2f}',
            'transaction_id': transaction.id,
            'subtotal': total,
            'gst': gst,
            'grand_total': grand_total,
            'payment_method': payment_method,
            'time': get_ist_time().strftime('%d %b %Y %I:%M %p')
        }
        
        # Add UPI transaction ID for online payments
        if payment_method == 'online':
            response_data['upi_transaction_id'] = 'UPI' + str(transaction.id) + str(int(get_ist_time().timestamp()))[-6:]

        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error processing sale: {str(e)}'})
    
# ===================== USERS LIST =====================
@app.route('/users')
def users():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

# ===================== SALES HISTORY =====================
@app.route('/sales')
def sales():
    """Display sales history"""
    # Get filter parameters
    date_filter = request.args.get('date', '')
    
    if date_filter:
        # Filter by specific date
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        transactions = Transaction.query.filter(
            db.func.date(Transaction.date) == filter_date
        ).order_by(Transaction.date.desc()).all()
    else:
        # Show all transactions
        transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    
    # Calculate totals
    total_sales = sum(t.total for t in transactions)
    avg_sale = total_sales / len(transactions) if transactions else 0
    
    # Format dates for display
    for transaction in transactions:
        if transaction.date:
            transaction.date_ist = transaction.date.astimezone(IST).strftime('%d %b %Y %I:%M %p')
    
    return render_template('sales.html', 
                         transactions=transactions,
                         total_sales=total_sales,
                         avg_sale=avg_sale,
                         filter_date=date_filter,
                         ist_time=get_ist_time().strftime('%d %b %Y %I:%M %p'))

@app.route('/sale_details/<int:id>')
def sale_details(id):
    """Get details of a specific sale (for AJAX)"""
    transaction = Transaction.query.get_or_404(id)
    return jsonify({
        'id': transaction.id,
        'date': transaction.date.astimezone(IST).strftime('%d %b %Y %I:%M %p'),
        'total': transaction.total,
        'items': transaction.items
    })

# ===================== SAMPLE PRODUCTS =====================
@app.route('/add_sample_products')
def add_sample_products():
    """Add sample grocery products to the database"""
    
    # Check if products already exist
    if Product.query.count() > 0:
        flash('Sample products already exist in the database!', 'info')
        return redirect(url_for('products'))
    
    sample_products = [
        # Dairy Products
        {"name": "Milk", "category": "Dairy", "price": 60.0, "stock": 50},
        {"name": "Butter", "category": "Dairy", "price": 80.0, "stock": 30},
        {"name": "Cheese", "category": "Dairy", "price": 120.0, "stock": 25},
        {"name": "Curd", "category": "Dairy", "price": 40.0, "stock": 40},
        {"name": "Paneer", "category": "Dairy", "price": 100.0, "stock": 20},
        {"name": "Cream", "category": "Dairy", "price": 90.0, "stock": 15},
        {"name": "Yogurt", "category": "Dairy", "price": 50.0, "stock": 35},
        {"name": "Buttermilk", "category": "Dairy", "price": 30.0, "stock": 25},
        
        # Vegetables
        {"name": "Potato", "category": "Vegetables", "price": 30.0, "stock": 100},
        {"name": "Tomato", "category": "Vegetables", "price": 40.0, "stock": 80},
        {"name": "Onion", "category": "Vegetables", "price": 35.0, "stock": 90},
        {"name": "Carrot", "category": "Vegetables", "price": 45.0, "stock": 60},
        {"name": "Cabbage", "category": "Vegetables", "price": 25.0, "stock": 40},
        {"name": "Cauliflower", "category": "Vegetables", "price": 50.0, "stock": 35},
        {"name": "Spinach", "category": "Vegetables", "price": 20.0, "stock": 45},
        {"name": "Capsicum", "category": "Vegetables", "price": 60.0, "stock": 30},
        {"name": "Brinjal", "category": "Vegetables", "price": 35.0, "stock": 40},
        {"name": "Ladyfinger", "category": "Vegetables", "price": 40.0, "stock": 35},
        {"name": "Cucumber", "category": "Vegetables", "price": 25.0, "stock": 45},
        {"name": "Pumpkin", "category": "Vegetables", "price": 30.0, "stock": 25},
        {"name": "Radish", "category": "Vegetables", "price": 30.0, "stock": 30},
        {"name": "Beetroot", "category": "Vegetables", "price": 40.0, "stock": 25},
        {"name": "Green Peas", "category": "Vegetables", "price": 60.0, "stock": 40},
        {"name": "French Beans", "category": "Vegetables", "price": 50.0, "stock": 35},
        
        # Fruits
        {"name": "Apple", "category": "Fruits", "price": 120.0, "stock": 50},
        {"name": "Banana", "category": "Fruits", "price": 40.0, "stock": 100},
        {"name": "Orange", "category": "Fruits", "price": 80.0, "stock": 60},
        {"name": "Mango", "category": "Fruits", "price": 150.0, "stock": 30},
        {"name": "Grapes", "category": "Fruits", "price": 90.0, "stock": 45},
        {"name": "Pomegranate", "category": "Fruits", "price": 110.0, "stock": 35},
        {"name": "Watermelon", "category": "Fruits", "price": 50.0, "stock": 20},
        {"name": "Papaya", "category": "Fruits", "price": 45.0, "stock": 25},
        {"name": "Pineapple", "category": "Fruits", "price": 80.0, "stock": 15},
        {"name": "Strawberry", "category": "Fruits", "price": 200.0, "stock": 20},
        {"name": "Kiwi", "category": "Fruits", "price": 180.0, "stock": 25},
        {"name": "Pear", "category": "Fruits", "price": 130.0, "stock": 30},
        {"name": "Peach", "category": "Fruits", "price": 140.0, "stock": 25},
        {"name": "Plum", "category": "Fruits", "price": 120.0, "stock": 30},
        {"name": "Cherry", "category": "Fruits", "price": 250.0, "stock": 15},
        
        # Staples
        {"name": "Rice", "category": "Staples", "price": 80.0, "stock": 100},
        {"name": "Wheat Flour", "category": "Staples", "price": 50.0, "stock": 80},
        {"name": "Sugar", "category": "Staples", "price": 45.0, "stock": 70},
        {"name": "Salt", "category": "Staples", "price": 20.0, "stock": 60},
        {"name": "Oil", "category": "Staples", "price": 120.0, "stock": 40},
        {"name": "Dal", "category": "Staples", "price": 90.0, "stock": 50},
        {"name": "Besan", "category": "Staples", "price": 60.0, "stock": 35},
        {"name": "Sooji", "category": "Staples", "price": 40.0, "stock": 30},
        
        # Beverages
        {"name": "Tea", "category": "Beverages", "price": 200.0, "stock": 40},
        {"name": "Coffee", "category": "Beverages", "price": 300.0, "stock": 30},
        {"name": "Juice", "category": "Beverages", "price": 80.0, "stock": 45},
        {"name": "Cold Drink", "category": "Beverages", "price": 40.0, "stock": 60},
        {"name": "Water Bottle", "category": "Beverages", "price": 20.0, "stock": 100},
        
        # Snacks
        {"name": "Biscuits", "category": "Snacks", "price": 30.0, "stock": 80},
        {"name": "Chips", "category": "Snacks", "price": 20.0, "stock": 90},
        {"name": "Namkeen", "category": "Snacks", "price": 50.0, "stock": 40},
        {"name": "Chocolate", "category": "Snacks", "price": 60.0, "stock": 50},
        {"name": "Noodles", "category": "Snacks", "price": 40.0, "stock": 45},
        
        # Personal Care
        {"name": "Soap", "category": "Personal Care", "price": 35.0, "stock": 60},
        {"name": "Shampoo", "category": "Personal Care", "price": 120.0, "stock": 40},
        {"name": "Toothpaste", "category": "Personal Care", "price": 80.0, "stock": 50},
        {"name": "Toothbrush", "category": "Personal Care", "price": 40.0, "stock": 70},
        {"name": "Deodrant", "category": "Personal Care", "price": 150.0, "stock":30}
    ]
    
    # Add all products to database
    for product_data in sample_products:
        product = Product(
            name=product_data["name"],
            category=product_data["category"],
            price=product_data["price"],
            stock=product_data["stock"]
        )
        db.session.add(product)
    
    db.session.commit()
    
    flash(f'Successfully added {len(sample_products)} sample products to the database!', 'success')
    return redirect(url_for('products'))

# ===================== API ENDPOINTS =====================
@app.route('/api/products')
def api_products():
    """API endpoint to get products (for AJAX calls)"""
    products = Product.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'category': p.category,
        'price': p.price,
        'stock': p.stock
    } for p in products])

@app.route('/api/product/<int:id>')
def api_product(id):
    """API endpoint to get single product"""
    product = Product.query.get_or_404(id)
    return jsonify({
        'id': product.id,
        'name': product.name,
        'category': product.category,
        'price': product.price,
        'stock': product.stock
    })

@app.route('/api/low_stock')
def api_low_stock():
    """API endpoint to get low stock products"""
    products = Product.query.filter(Product.stock < 10).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'stock': p.stock
    } for p in products])

@app.route('/api/current_time')
def api_current_time():
    """API endpoint to get current IST time"""
    return jsonify({
        'time': get_ist_time().strftime('%d %b %Y %I:%M %p'),
        'timestamp': get_ist_time().isoformat()
    })

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def not_found_error(error):
    flash('Page not found', 'warning')
    return redirect(url_for('dashboard'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    flash('An internal error occurred', 'danger')
    return redirect(url_for('dashboard'))

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def not_found_error(error):
    flash('Page not found', 'warning')
    return redirect(url_for('dashboard'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    flash('An internal error occurred', 'danger')
    return redirect(url_for('dashboard'))

# ===================== RUN =====================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database created successfully!")
        print("📊 GreenGrocer Management System")
        print("🚀 Server starting...")
        print(f"🕐 Current IST Time: {get_ist_time().strftime('%d %b %Y %I:%M %p')}")
        
        # Check if products exist, if not prompt to add
        product_count = Product.query.count()
        if product_count == 0:
            print("\n⚠️  No products found in database!")
            print("👉 To add sample products, visit: http://127.0.0.1:5000/add_sample_products")
        else:
            print(f"\n📦 {product_count} products available in database")
    
    # Production settings for Render
    import os
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") == "development"
    
    print(f"\n🌐 Server will run on port: {port}")
    print(f"🔧 Debug mode: {'ON' if debug_mode else 'OFF'}")
    print("=" * 50)
    
    app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)