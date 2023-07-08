from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import Flask, request, render_template, redirect, url_for, session
from flask_dance.contrib.facebook import make_facebook_blueprint, facebook
import mysql.connector
from mysql.connector import Error
from werkzeug.middleware.proxy_fix import ProxyFix
import shopify
import csv

db_host = 'client-database.cpaiqbqfarfd.ap-south-1.rds.amazonaws.com'
db_name = 'schema1'
db_user = 'admin'
db_password = 'password'
db_port = 3306

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'


app.config['FACEBOOK_OAUTH_CLIENT_ID'] = '297966449277890'
app.config['FACEBOOK_OAUTH_CLIENT_SECRET'] = '16c671a901ee984a6add3c619f46e927'
# Force HTTPS redirection
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

blueprint = make_facebook_blueprint(scope='email')
app.register_blueprint(blueprint, url_prefix='/login')
cart = []

# Connect to Shopify store
shop_url = 'https://digitalmalls.in'
api_key = 'd6ffb16e3ef0d05e90554317b51110d2'
api_password = '9dd2d12086f7d0b1c2505de926e44f09'



shopify.ShopifyResource.set_site(shop_url)
shopify.ShopifyResource.set_user(api_key)
shopify.ShopifyResource.set_password(api_password)


@app.context_processor
def inject_facebook():
    return {'facebook': facebook}

# Facebook login callback route
@app.route("/login/facebook")
def facebook_login():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        return redirect(url_for("base"))

@app.route('/')
def home():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        data = facebook.get('/me?fields=id,name,email,birthday,interested_in').json()
        name = data.get('name')
        id = data.get('id')
        email = data.get('email')
        birthday = data.get('birthday')
        interested_in = data.get('interested_in')

        # Print user information in the console
        print("Facebook login data:")
        print("id:", id)
        print("Name:", name)
        print("Email:", email)
        print("Birthday:", birthday)
        print("Interested In:", interested_in)

        # Store user ID and username in session
        session['user_id'] = id
        session['username'] = name

        # Retrieve the user's coins from the MySQL database
        try:
            connection = mysql.connector.connect(
                host=db_host,
                database=db_name,
                user=db_user,
                password=db_password,
                port=db_port
            )

            if connection.is_connected():
                # Query the database to retrieve the user's balance
                cursor = connection.cursor()
                cursor.execute(f"SELECT coins FROM users WHERE id = '{id}'")
                result = cursor.fetchone()

                if result:
                    coins = result[0]
                else:
                    coins = 0

                cursor.close()
                connection.close()

                return render_template('coupon.html', coins=coins, username=name)
            else:
                return "Failed to connect to the database."
        except Error as e:
            print("Error connecting to the database:", e)
            return "An error occurred while connecting to the database."

# Coupon redemption
@app.route('/coupon/<couponcode>', methods=['GET'])
def coupon_redemption(couponcode):
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        # Extract bill amount from coupon code
        bill_amount = int(couponcode.split('_')[1])

        # Get available offers
        products = get_available_offers(bill_amount)
        

        return render_template('coupon.html', products=products)

def get_product_by_id(id):
    products = shopify.Product.find()
    for product in products:
        if product.id == id:
            return product
    return None


@app.route('/checkout', methods=['GET'])
def checkout():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        # Retrieve the cart from session
        cart = session.get('cart', [])

        # Calculate the total coins
        coins = request.args.get('coins')
        

        return render_template('checkout.html', cart=cart, total_coins=coins)



@app.route('/proceed_to_checkout', methods=['GET'])
def proceed_to_checkout():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        # Retrieve the cart from session or create a new one
        cart = session.get('cart', [])

        # Check if the cart is empty
        if not cart:
            flash('Your cart is empty.', 'error')
            return redirect(url_for('view_cart'))

        return redirect(url_for('checkout'))
    
# Logout route
@app.route('/logout')
def logout():
    if facebook.authorized:
        # Clear the session
        session.clear()
        flash('You have been logged out.', 'success')
    else:
        flash('You are not logged in.', 'warning')

    # Redirect to your home page
    return redirect(url_for('home'))

@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        name = request.form['name']
        mobile = request.form['mobile']

        # Retrieve the cart from session
        cart = session.get('cart', [])


        # Get the product details from the cart
        product_ids = [item['product_id'] for item in cart]
        product_names = [get_product_name(product_id) for product_id in product_ids]
        print(product_names)
        print(product_ids)
        # Save order details to CSV
        save_order_to_csv(name, mobile, product_names=product_names, product_ids=product_ids)


        # Clear the cart
        session['cart'] = []

        return render_template('confirmation.html', name=name, mobile=mobile)


@app.route('/order_confirmation/<name>')
def order_confirmation(name):
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        return render_template('confirmation.html', name=name)



@app.route('/add_to_cart/<int:product_id>', methods=['GET', 'POST'])
def add_to_cart(product_id):
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        # Retrieve the product based on the product_id
        product = get_product_by_id(product_id)
        
        # Add the product to the cart
        if product:
            add_product_to_cart(product)
            return redirect(url_for('view_cart'))  # Change 'cart' to 'view_cart'
        else:
            flash('Product not found', 'error')
            return redirect(url_for('coupon_redemption'))
    
@app.route('/view_cart', methods=['GET'])
def view_cart():
    if not facebook.authorized:
        return "You are not logged in. <a href='/login/facebook'>Click here to log in</a>"
    else:
        # Retrieve the cart from session or create a new one
        cart = session.get('cart', [])

        return render_template('cart.html', cart=cart)



def add_product_to_cart(product):
    # Retrieve the current cart from session or create a new one
    cart = session.get('cart', [])

    # Check if the product is already in the cart
    for item in cart:
        if item['product_id'] == product.id:
            # If the product is already in the cart, increase its quantity
            item['quantity'] += 1
            break
    else:
        # If the product is not in the cart, add it as a new item
        variant = product.variants[0]  # Assuming the first variant has the price
        cart.append({
            'product_id': product.id,
            'product_name': product.title,
            'product_price': variant.price,
            'quantity': 1
        })

    # Update the cart in the session
    session['cart'] = cart

def get_product_name(product_id):
    product = get_product_by_id(product_id)
    return product.title

# Get available offers based on bill amount
def get_available_offers(bill_amount):
    # Fetch products from Shopify store
    products = shopify.Product.find()

    # Filter products based on bill amount
    available_offers = []
    for product in products:
        variant_price = float(product.variants[0].price)
        coins = int(variant_price)
        if coins <= int(bill_amount):
            product.price = coins
            available_offers.append(product)

    return available_offers

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    session['cart'] = []
    return redirect(url_for('view_cart'))

# Calculate total coins based on cart items
def calculate_total_coins(cart):
    total_coins = 0
    for item in cart:
        total_coins += int(item['product_price'])
    return total_coins



def save_order_to_csv(name, mobile, product_names, product_ids):
    # Check if all parameters have values
    if name and mobile and product_names and product_ids:
        fieldnames = ['Name', 'Mobile', 'Product Name', 'Product ID']

        with open('orders.csv', 'a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)

            # Check if the file is empty and write the header row
            if file.tell() == 0:
                writer.writeheader()

            # Iterate over the product names and IDs
            for product_name, product_id in zip(product_names, product_ids):
                writer.writerow({'Name': name, 'Mobile': mobile, 'Product Name': product_name, 'Product ID': product_id})

# Cart management functions (to be implemented)

def get_cart_from_session():
    # Implement the logic to retrieve the cart from session
    return []

def clear_cart():
    # Implement the logic to clear the cart
    pass

if __name__ == '__main__':
    app.run(debug=True,ssl_context=('localhost.pem', 'localhost-key.pem'))