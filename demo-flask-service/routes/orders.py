from flask import Blueprint, jsonify, request

orders_bp = Blueprint("orders", __name__)

ORDERS = [
    {"id": 1, "user_id": 1, "product_id": 2, "quantity": 1},
    {"id": 2, "user_id": 2, "product_id": 1, "quantity": 2},
]


@orders_bp.route("/", methods=["GET"])
def list_orders():
    """List all orders"""
    return jsonify(ORDERS)


@orders_bp.route("/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """Get order details"""
    order = next((o for o in ORDERS if o["id"] == order_id), None)
    if not order:
        return {"error": "Order not found"}, 404
    return jsonify(order)


@orders_bp.route("/", methods=["POST"])
def create_order():
    """Create a new order"""
    data = request.get_json()
    new_order = {
        "id": len(ORDERS) + 1,
        "user_id": data["user_id"],
        "product_id": data["product_id"],
        "quantity": data["quantity"]
    }
    ORDERS.append(new_order)
    return jsonify(new_order), 201
