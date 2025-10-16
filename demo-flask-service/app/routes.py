from flask import Blueprint, jsonify, request

bp = Blueprint('api', __name__)

@bp.route('/health', methods=['GET'])
def health_check():
    """
    Check if the service is healthy.
    """
    return jsonify({"status": "ok"}), 200

@bp.route('/users', methods=['GET'])
def list_users():
    """
    Get a list of all users.
    """
    users = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    return jsonify(users), 200

@bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """
    Get details of a user by ID.
    """
    return jsonify({"id": user_id, "name": "Sample User"}), 200

@bp.route('/users', methods=['POST'])
def create_user():
    """
    Create a new user.
    """
    data = request.json
    return jsonify({"message": "User created", "user": data}), 201
