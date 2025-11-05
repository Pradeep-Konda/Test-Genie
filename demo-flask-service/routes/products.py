from flask import Blueprint, jsonify, request

products_bp = Blueprint("products", __name__)

PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 999.99},
    {"id": 2, "name": "Phone", "price": 499.99},
]


@products_bp.route("/", methods=["GET"])
def list_products():
    """List all products"""
    return jsonify(PRODUCTS)


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """Get product by ID"""
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        return {"error": "Product not found"}, 404
    return jsonify(product)


@products_bp.route("/", methods=["POST"])
def add_product():
    """Add a new product"""
    data = request.get_json()
    new_product = {"id": len(PRODUCTS) + 1, "name": data["name"], "price": data["price"]}
    PRODUCTS.append(new_product)
    return jsonify(new_product), 201
