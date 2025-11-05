from flask import Flask
from routes.users import users_bp
from routes.products import products_bp
from routes.orders import orders_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Register Blueprints
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return {"status": "ok"}, 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
