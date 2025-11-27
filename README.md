# Mock Computer Part Pricing API

A lightweight Python Flask microservice designed to serve as a mock backend for a C# application (https://github.com/KAZABUILD/KAZABUILD). It provides pricing data for computer components (CPUs, GPUs, RAM) by querying a local SQLite database and applying dynamic pricing formulas based on component specifications.

## specific_usage
### Option 1: Running with Docker (Recommended)
1.  **Build the image:**
    ```bash
    docker build -t mock-price-api .
    ```
2.  **Run the container:**
    ```bash
    docker run -p 5000:5000 mock-price-api
    ```

### Option 2: Running Locally (Python)
1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Start the server:
    ```bash
    python app.py
    ```

## API Documentation

### Get Component Price
Returns the calculated price of a component in PLN.

* **Endpoint:** `/get-price`
* **Method:** `POST`
* **Content-Type:** `application/json`

#### Request Body
```json
{
  "type": "GPU",
  "name": "RTX 4070"
}