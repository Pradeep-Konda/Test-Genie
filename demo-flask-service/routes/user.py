from flask import Blueprint, jsonify, request

users_bp = Blueprint("users", __name__)

USERS = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
]


@users_bp.route("/", methods=["GET"])
def list_users():
    """List all users"""
    return jsonify(USERS)


@users_bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """Get user by ID"""
    user = next((u for u in USERS if u["id"] == user_id), None)
    if not user:
        return {"error": "User not found"}, 404
    return jsonify(user)


@users_bp.route("/", methods=["POST"])
def create_user():
    """Create a new user"""
    data = request.get_json()
    new_user = {"id": len(USERS) + 1, "name": data["name"], "email": data["email"]}
    USERS.append(new_user)
    return jsonify(new_user), 201
