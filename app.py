

from flask import Flask, request, jsonify, render_template, send_from_directory
import pandas as pd
from sklearn.linear_model import LinearRegression
from fuzzywuzzy import fuzz
import mysql.connector
from flask_cors import CORS
import logging
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG) 
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}})



app.config['UPLOAD_FOLDER'] = 'uploaded_images'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="food_app_ml"
    )


# Initialize the items table if it doesn’t exist
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS items (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      name VARCHAR(100),
                      price FLOAT,
                      image VARCHAR(255),
                      demand INT,
                      stock INT
                      )''')
    conn.commit()
    cursor.close()
    conn.close()

# Initialize Database on startup
initialize_database()

# Sample data for the regression model
data = pd.DataFrame({
    'demand': [10, 50, 30, 100, 60], 
    'stock': [100, 80, 40, 30, 60],
    'price': [10, 15, 12, 18, 16]
})
X = data[['demand', 'stock']]
y = data['price']
model = LinearRegression()
model.fit(X, y)


# Fetch user order history based on email
def fetch_user_history(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT oi.item_id
    FROM orders o
    JOIN order_item oi ON o.id = oi.orders_id
    JOIN ourusers u ON o.user_id = u.id
    WHERE u.email = %s
    """
    cursor.execute(query, (email,))
    user_items = cursor.fetchall()
    
    conn.close()
    return [item['item_id'] for item in user_items]

# Fetch all items with their average rating and tags
def fetch_items_with_ratings():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT 
        i.id, 
        i.name, 
        i.price, 
        GROUP_CONCAT(t.tags) AS tags,
        COALESCE(AVG(r.rating), 0) AS average_rating
    FROM item i
    LEFT JOIN item_review r ON i.id = r.item_id
    LEFT JOIN item_tags t ON i.id = t.item_id
    GROUP BY i.id
    """
    cursor.execute(query)
    items = cursor.fetchall()
    
    for item in items:
        if item['tags']:
            item['tags'] = item['tags'].split(',')
        else:
            item['tags'] = []
    
    conn.close()
    return items

# Rank items based on user history and average rating
def rank_items(items, user_history):
    purchased = [item for item in items if item['id'] in user_history]
    not_purchased = [item for item in items if item['id'] not in user_history]

    purchased = sorted(purchased, key=lambda x: x.get('average_rating', 0), reverse=True)
    not_purchased = sorted(not_purchased, key=lambda x: x.get('average_rating', 0), reverse=True)

    return purchased + not_purchased

# Auto-suggestion logic for ML-based suggestions
def auto_suggestion(user_input, items, user_history):
    # ML-based: Fuzzy matching on name and tags
    ml_name_matches = [item for item in items if fuzz.partial_ratio(user_input.lower(), item['name'].lower()) > 70]
    ml_tag_matches = [item for item in items if item['tags'] and any(fuzz.partial_ratio(user_input.lower(), tag.lower()) > 70 for tag in item['tags'])]

    ml_ranked_name_matches = rank_items(ml_name_matches, user_history)
    ml_ranked_tag_matches = rank_items(ml_tag_matches, user_history)

    return {
        "ml_based": {
            "name_matches": ml_ranked_name_matches,
            "tag_matches": ml_ranked_tag_matches
        }
    }

@app.route('/suggest', methods=['GET'])
def suggest():
    user_input = request.args.get('query')
    if not user_input:
        return jsonify({"ml_based": {"name_matches": [], "tag_matches": []}})
    
    user_email = "test12@gmail.com"  # Replace with actual session-based email for logged-in user
    
    try:
        items = fetch_items_with_ratings()
        user_history = fetch_user_history(user_email)
        suggestions = auto_suggestion(user_input, items, user_history)
        return jsonify(suggestions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# API endpoint for prediction based on demand and stock
@app.route('/predict', methods=['POST'])
def predict():
    demand = request.json.get('demand')
    stock = request.json.get('stock')
    input_data = pd.DataFrame([[demand, stock]], columns=['demand', 'stock'])
    predicted_price = model.predict(input_data)
    return jsonify(predicted_price=predicted_price[0])
# API to handle adding items with image upload and retrieving items
@app.route('/items', methods=['POST', 'GET'])
def items():
    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        demand = int(request.form.get('demand', 0))
        stock = int(request.form.get('stock', 0))
        
        # Handle image upload
        image_file = request.files.get('image')
        if image_file:
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(image_path)
        else:
            filename = None  # No image uploaded

        # Insert item into the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO item (name, price, image, demand, stock) VALUES (%s, %s, %s, %s, %s)",
            (name, price, filename, demand, stock)
        )
        conn.commit()
        item_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({
            'id': item_id,
            'name': name,
            'price': price,
            'image': filename,
            'demand': demand,
            'stock': stock
        })

    elif request.method == 'GET':
        # Retrieve items from the database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM item")
        items = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(items)


# Serve uploaded images
@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.json
    demand = int(data.get('demand', 0))
    stock = int(data.get('stock', 0))
    price = float(data.get('price', 0))

    # Update the item in the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET demand = %s, stock = %s, price = %s WHERE id = %s",
        (demand, stock, price, item_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Item updated successfully"})


# Test route
@app.route('/', methods=['GET'])
def hello():
    return jsonify(message="Hello, World!")

if __name__ == '__main__':
    app.run(debug=True)
