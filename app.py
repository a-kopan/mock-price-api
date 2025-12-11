import sqlite3
import json
import os
import glob
import logging
from flask import Flask, request, jsonify, send_from_directory, url_for

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    logger.info("Initializing database connection...")
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
        logger.info(f"Database empty. Seeding from {DATA_SOURCE_DIR}...")
        seed_database(conn)
    else:
        logger.info(f"Database already contains {count} items. Skipping seed.")
        
    conn.close()

def seed_database(conn):
    """
    Walks through the DATA_SOURCE_DIR, reads every JSON file, 
    and inserts it into the database.
    """
    if not os.path.exists(DATA_SOURCE_DIR):
        logger.warning(f"WARNING: Data source directory '{DATA_SOURCE_DIR}' not found. Database will be empty.")
        return

    cursor = conn.cursor()
    inserted_count = 0

    # Walk through each folder in the open-db directory
    logger.info(f"Walking through directory: {DATA_SOURCE_DIR}")
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
                    logger.error(f"Error loading {file_path}: {e}")

    conn.commit()
    logger.info(f"Successfully seeded {inserted_count} components into the database.")

# Pricing Logic
def get_safe_val(data, path, default=0):
    try:
        keys = path.split('.')
        current = data
        for key in keys:
            if current is None: return default
            current = current.get(key)
        return current if current is not None else default
    except Exception as e:
        # Debug level logging for safe value extraction failures to avoid noise
        logger.debug(f"Error retrieving path '{path}': {e}")
        return default

def calculate_price(component_type, specs):
    price = 0.0
    
    if component_type == 'CPU':
        cores = get_safe_val(specs, 'cores.total', 4)
        perf = get_safe_val(specs, 'cores.performance', cores)  # assume all performance if missing
        boost = get_safe_val(specs, 'clocks.performance.boost', 3.0)

        # Base: cheap dual/quad cores
        price = 100 + (cores * 40) + (perf * 20) + ((boost - 3.0) * 80)

        # Clamp prices
        price = max(150, min(price, 3500))

    elif component_type == 'GPU':
        vram = get_safe_val(specs, 'memory', 4)
        bus = get_safe_val(specs, 'memory_bus', 128)

        price = 150 + (vram * 60) + (bus * 0.4)

        chipset = get_safe_val(specs, 'chipset', '')
        if any(x in chipset for x in ['4090', '4080', '7900 XTX', '7900 XT']):
            price += 3000

        price = max(250, min(price, 9000))

    elif component_type == 'Motherboard':
        ram_slots = get_safe_val(specs, 'memory.slots', 2)
        m2 = len(specs.get('m2_slots') or [])
        pcie = len(specs.get('pcie_slots') or [])
        wifi = get_safe_val(specs, 'wireless_networking', False)

        price = 150 + (ram_slots * 30) + (m2 * 60) + (pcie * 20) + (150 if wifi else 0)

        price = max(200, min(price, 1500))

    elif component_type == 'RAM':
        qty = get_safe_val(specs, 'modules.quantity', 1)
        cap = get_safe_val(specs, 'modules.capacity_gb', 8)
        speed = get_safe_val(specs, 'speed', 3200)

        total_gb = qty * cap
        price = 40 + (total_gb * 6) + ((speed - 2400) * 0.02)

        price = max(60, min(price, 600))

    elif component_type == 'Storage':
        cap = get_safe_val(specs, 'capacity', 500)
        ssd = 'SSD' in get_safe_val(specs, 'type', 'HDD')
        nvme = get_safe_val(specs, 'nvme', False)

        if nvme:
            per_gb = 0.22
        elif ssd:
            per_gb = 0.18
        else:
            per_gb = 0.10

        price = 30 + cap * per_gb
        price = max(50, min(price, 1000))

    elif component_type == 'PSU':
        watts = get_safe_val(specs, 'wattage', 500)
        modular = get_safe_val(specs, 'modular', '')

        price = 120 + (watts * 0.3) + (80 if 'Full' in modular else 0)
        price = max(150, min(price, 800))

    elif component_type == 'PCCase':
        vol = get_safe_val(specs, 'volume', 40)
        glass = get_safe_val(specs, 'has_transparent_side_panel', False)

        price = 100 + (vol * 2) + (60 if glass else 0)
        price = max(120, min(price, 500))

    elif component_type == 'CPUCooler':
        if get_safe_val(specs, 'water_cooled', False):
            rad = get_safe_val(specs, 'radiator_size', 240)
            price = 200 + rad * 0.7
        else:
            height = get_safe_val(specs, 'height', 150)
            price = 60 + height * 0.6

        price = max(80, min(price, 600))
            
    elif component_type == 'CaseFan':
        size = get_safe_val(specs, 'size', 120)
        qty = get_safe_val(specs, 'quantity', 1)

        price = (size * 0.25) * qty
        price = max(15, min(price, 200))

    else:
        # Default for unknown types
        logger.warning(f"Unknown component type '{component_type}' encountered in price calc.")
        price = 150.0

    return round(price, 2)

@app.route('/images/<path:filename>')
def serve_image(filename):
    """
    Serves the actual image file from the local directory.
    """
    logger.info(f"Serving image: {filename}")
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
        logger.warning("Received invalid price request: Missing name or type.")
        return jsonify({"error": "Invalid request. 'name' and 'type' required."}), 400

    req_name = data['name']
    req_type = data['type']
    
    logger.info(f"Requesting price for: Type='{req_type}', Name='{req_name}'")

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
        
        logger.info(f"Found '{req_name}': Calculated Price {price_val} PLN")
        
        return jsonify({
            "status": 200,
            "component": req_name,
            "type": req_type,
            "price": price_val,
            "currency": "PLN",
            "imageUrl": img_url 
        }), 200
    else:
        logger.warning(f"Component not found in DB: Type='{req_type}', Name='{req_name}'")
        return jsonify({"status": 404, "error": "Component not found"}), 404

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    init_db()
    port = int(os.environ.get('PORT', 5000)) 
    logger.info(f"Running on port {port}")
    app.run(host='0.0.0.0', port=port)