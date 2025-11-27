import sqlite3
import json
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration
DB_NAME = 'components.db'
# Using /app/data for Docker volume persistence, or local folder if running locally
DB_PATH = os.path.join(os.environ.get('DATA_DIR', '.'), DB_NAME)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database.
    Creates table if not exists and seeds it with mock data if empty.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create table with a JSON column for flexible specs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            specs TEXT NOT NULL, -- Storing attributes as JSON string
            base_cost REAL NOT NULL -- A base manufacturing cost to start calculations from
        )
    ''')
    
    # Check if empty, if so, seed with mock data
    cursor.execute('SELECT count(*) FROM components')
    if cursor.fetchone()[0] == 0:
        print("Seeding database with mock data...")
        mock_data = [
            # CPU: Pricing depends on Cores/Threads
            ('CPU', 'Ryzen 7 5800X', json.dumps({"cores": 8, "threads": 16}), 800.0),
            ('CPU', 'Intel Core i9-13900K', json.dumps({"cores": 24, "threads": 32}), 1500.0),
            
            # GPU: Pricing depends on VRAM
            ('GPU', 'RTX 4070', json.dumps({"vram_gb": 12, "generation": 40}), 2000.0),
            ('GPU', 'RTX 3060', json.dumps({"vram_gb": 12, "generation": 30}), 1000.0),
            
            # RAM: Pricing depends on Capacity
            ('RAM', 'Corsair Vengeance', json.dumps({"capacity_gb": 32, "speed": 3600}), 300.0)
        ]
        cursor.executemany('INSERT INTO components (type, name, specs, base_cost) VALUES (?, ?, ?, ?)', mock_data)
        conn.commit()
        
    conn.close()

def calculate_price(component_type, base_cost, specs):
    """
    Calculates final price based on type-specific attributes.
    """
    price = base_cost
    
    if component_type == 'CPU':
        # Example Formula: Base + (Cores * 50) + (Threads * 20)
        cores = specs.get('cores', 0)
        threads = specs.get('threads', 0)
        price += (cores * 50) + (threads * 20)
        
    elif component_type == 'GPU':
        # Example Formula: Base + (VRAM * 100)
        vram = specs.get('vram_gb', 0)
        price += (vram * 100)
        
    elif component_type == 'RAM':
        # Example Formula: Base + (Capacity * 10)
        capacity = specs.get('capacity_gb', 0)
        price += (capacity * 10)

    return round(price, 2)

@app.route('/get-price', methods=['POST'])
def get_component_price():
    data = request.get_json()
    
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({"error": "Invalid request. 'name' and 'type' required."}), 400

    req_name = data['name']
    req_type = data['type']

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch component
    cursor.execute('SELECT * FROM components WHERE name = ? AND type = ?', (req_name, req_type))
    row = cursor.fetchone()
    conn.close()

    if row:
        # Component found
        specs = json.loads(row['specs'])
        base_cost = row['base_cost']
        
        # Calculate dynamic price
        final_price = calculate_price(req_type, base_cost, specs)
        
        return jsonify({
            "status": 200,
            "component": req_name,
            "price": final_price,
            "currency": "PLN"
        }), 200
    else:
        # Component not found
        return jsonify({"status": 404, "error": "Component not found"}), 404

if __name__ == '__main__':
    # Initialize DB on startup
    init_db()
    # Host='0.0.0.0' is required for Docker to expose the port
    app.run(host='0.0.0.0', port=5000)