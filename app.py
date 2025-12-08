import sqlite3
import json
import os
import glob
from flask import Flask, request, jsonify, send_from_directory, url_for

app = Flask(__name__)

# Configuration 
DB_NAME = 'components.db'
DB_DIR = os.environ.get('DB_DIR', '.')
DB_PATH = os.path.join(DB_DIR, DB_NAME)
DATA_SOURCE_DIR = os.environ.get('DATA_SOURCE_DIR', os.path.join('.', 'data', 'open-db'))
IMAGES_DIR = os.environ.get('IMAGES_DIR', os.path.join('.', 'images'))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database and seeds it if empty.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create the table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,         -- Matches folder name (e.g., 'CPU', 'GPU')
            name TEXT NOT NULL,         -- Matches metadata.name
            specs TEXT NOT NULL,        -- The full JSON content
            base_cost REAL DEFAULT 0
        )
    ''')
    conn.commit()

    # Check if we need to seed data
    cursor.execute('SELECT count(*) FROM components')
    count = cursor.fetchone()[0]
    
    if count == 0:
        print(f"Database empty. Seeding from {DATA_SOURCE_DIR}...")
        seed_database(conn)
    else:
        print(f"Database already contains {count} items. Skipping seed.")
        
    conn.close()

def seed_database(conn):
    """
    Walks through the DATA_SOURCE_DIR, reads every JSON file, 
    and inserts it into the database.
    """
    if not os.path.exists(DATA_SOURCE_DIR):
        print(f"WARNING: Data source directory '{DATA_SOURCE_DIR}' not found. Database will be empty.")
        return

    cursor = conn.cursor()
    inserted_count = 0

    # Walk through each folder in the open-db directory
    for root, dirs, files in os.walk(DATA_SOURCE_DIR):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                
                component_type = os.path.basename(root)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        
                        # Extract Name safely
                        name = content.get('metadata', {}).get('name', 'Unknown Component')
                        
                        # Insert into DB
                        cursor.execute(
                            "INSERT INTO components (type, name, specs) VALUES (?, ?, ?)", 
                            (component_type, name, json.dumps(content))
                        )
                        inserted_count += 1
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

    conn.commit()
    print(f"Successfully seeded {inserted_count} components into the database.")

# Pricing Logic
def get_safe_val(data, path, default=0):
    try:
        keys = path.split('.')
        current = data
        for key in keys:
            if current is None: return default
            current = current.get(key)
        return current if current is not None else default
    except:
        return default

def calculate_price(component_type, specs):
    price = 0.0
    
    if component_type == 'CPU':
        cores = get_safe_val(specs, 'cores.total', 4)
        perf_cores = get_safe_val(specs, 'cores.performance', 0)
        boost = get_safe_val(specs, 'clocks.performance.boost', 3.0)
        price = 500 + (perf_cores * 150) + ((cores - perf_cores) * 50) + (boost * 200)

    elif component_type == 'GPU':
        vram = get_safe_val(specs, 'memory', 4)
        bus = get_safe_val(specs, 'memory_bus', 128)
        price = 1000 + (vram * 150) + (bus * 2)
        if '4090' in get_safe_val(specs, 'chipset', '') or '7900 XTX' in get_safe_val(specs, 'chipset', ''):
            price += 4000

    elif component_type == 'Motherboard':
        ram_slots = get_safe_val(specs, 'memory.slots', 2)
        m2_count = len(specs.get('m2_slots') or [])
        pcie_count = len(specs.get('pcie_slots') or [])
        price = 400 + (ram_slots * 50) + (m2_count * 100) + (pcie_count * 50)
        if get_safe_val(specs, 'wireless_networking'): price += 150

    elif component_type == 'RAM':
        qty = get_safe_val(specs, 'modules.quantity', 1)
        cap = get_safe_val(specs, 'modules.capacity_gb', 8)
        total = qty * cap
        price = 100 + (total * 12) + (get_safe_val(specs, 'speed', 3200) * 0.1)

    elif component_type == 'Storage':
        cap = get_safe_val(specs, 'capacity', 500)
        is_ssd = 'SSD' in get_safe_val(specs, 'type', 'HDD')
        per_gb = 0.4 if is_ssd else 0.15
        if get_safe_val(specs, 'nvme', False): per_gb = 0.55
        price = 100 + (cap * per_gb)

    elif component_type == 'PSU':
        watts = get_safe_val(specs, 'wattage', 500)
        price = 200 + (watts * 0.5) + (200 if 'Full' in get_safe_val(specs, 'modular', '') else 0)

    elif component_type == 'PCCase':
        vol = get_safe_val(specs, 'volume', 40)
        glass = get_safe_val(specs, 'has_transparent_side_panel', False)
        price = 200 + (vol * 5) + (100 if glass else 0)

    elif component_type == 'CPUCooler':
        if get_safe_val(specs, 'water_cooled', False):
            price = 300 + (get_safe_val(specs, 'radiator_size', 240) * 1.5)
        else:
            price = 100 + (get_safe_val(specs, 'height', 150) * 1.0)
            
    elif component_type == 'CaseFan':
        price = (get_safe_val(specs, 'size', 120) * 0.4) * get_safe_val(specs, 'quantity', 1)

    else:
        # Default for unknown types
        price = 150.0

    return round(price, 2)

@app.route('/images/<path:filename>')
def serve_image(filename):
    """
    Serves the actual image file from the local directory.
    """
    return send_from_directory(IMAGES_DIR, filename)

def get_image_url(component_type, component_name):
    """
    Logic to map a component to an image filename.
    Currently defaults to {Type}.jpg (e.g., CPU.jpg).
    """
    # Map by Type
    filename = f"{component_type}.jpg"

    # Generates a full URL
    return url_for('serve_image', filename=filename, _external=True)

# API routes
@app.route('/get-price', methods=['POST'])
def get_component_price():
    data = request.get_json()
    
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({"error": "Invalid request. 'name' and 'type' required."}), 400

    req_name = data['name']
    req_type = data['type']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT specs FROM components WHERE name = ? AND type = ?', (req_name, req_type))
    row = cursor.fetchone()
    conn.close()

    if row:
        specs = json.loads(row['specs'])
        
        # Calculate Price
        price_val = calculate_price(req_type, specs)
        
        # Generate Image URL
        img_url = get_image_url(req_type, req_name)
        
        return jsonify({
            "status": 200,
            "component": req_name,
            "type": req_type,
            "price": price_val,
            "currency": "PLN",
            "imageUrl": img_url 
        }), 200
    else:
        return jsonify({"status": 404, "error": "Component not found"}), 404

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=4900)