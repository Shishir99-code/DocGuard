"""Sample Flask application used as a test fixture for the parser."""

from flask import Blueprint, Flask

app = Flask(__name__)

# Blueprint with a declared url_prefix.
users_bp = Blueprint("users", __name__, url_prefix="/users")

# Blueprint with no declared prefix; prefix is supplied at registration time.
items_bp = Blueprint("items", __name__)


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/login", methods=["POST"])
def login():
    return {"token": "..."}


@users_bp.route("/")
def list_users():
    return []


@users_bp.route("/<int:user_id>", methods=["GET", "DELETE"])
def user_detail(user_id):
    return {"id": user_id}


@items_bp.route("/<item_id>", methods=["GET", "PUT"])
def item_detail(item_id):
    return {"id": item_id}


def report_view():
    return {"ok": True}


# Route registered via add_url_rule rather than a decorator.
app.add_url_rule("/reports/<int:report_id>", view_func=report_view, methods=["GET"])

# Register blueprints; items_bp gets its prefix here (overrides any declared prefix).
app.register_blueprint(users_bp)
app.register_blueprint(items_bp, url_prefix="/items")
