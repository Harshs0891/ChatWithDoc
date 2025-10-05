import os
import json
import logging
import uuid
from datetime import datetime
from functools import wraps
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    flash,
    send_file,
)
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from features.chat import chat_bp, get_chat_system

# Configure Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "military-doc-intelligence-2024")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max file size
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["TEMP_FOLDER"] = "temp"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("military_doc_system.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Create directories
for directory in [
    app.config["UPLOAD_FOLDER"],
    app.config["TEMP_FOLDER"],
    "database",
    "features",
]:
    os.makedirs(directory, exist_ok=True)


class DatabaseManager:
    """Database manager for user management and query logging"""

    DATABASE_PATH = "database/military_docs.db"

    def __init__(self):
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with all required tables"""
        with sqlite3.connect(self.DATABASE_PATH) as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    rank TEXT,
                    unit TEXT,
                    clearance_level INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """
            )

            # Query logs table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS query_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    session_id TEXT,
                    query TEXT,
                    response TEXT,
                    documents_used TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    classification TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """
            )

            # Document metadata table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS document_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    file_hash TEXT UNIQUE,
                    classification TEXT,
                    uploaded_by INTEGER,
                    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER,
                    page_count INTEGER,
                    FOREIGN KEY (uploaded_by) REFERENCES users (id)
                )
            """
            )

            # Create default admin user if not exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("admin",))
            if cursor.fetchone()[0] == 0:
                admin_hash = generate_password_hash("admin123")
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, rank, unit, clearance_level)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    ("admin", admin_hash, "Administrator", "HQ", 5),
                )

    def execute_query(self, query, params=None, fetch=False):
        """Execute database query with error handling"""
        try:
            with sqlite3.connect(self.DATABASE_PATH) as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if fetch:
                    return cursor.fetchall() if fetch == "all" else cursor.fetchone()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Database error: {e}")
            return None if fetch else 0


# Initialize components
db_manager = DatabaseManager()

# Register blueprint
app.register_blueprint(chat_bp)


# Decorators
def login_required(f):
    """Decorator to require user authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        user = db_manager.execute_query(
            "SELECT clearance_level FROM users WHERE id = ?",
            (session["user_id"],),
            fetch="one",
        )

        if not user or user[0] < 3:  # Require clearance level 3+
            flash("Access denied. Insufficient clearance level.", "error")
            return redirect(url_for("dashboard"))

        return f(*args, **kwargs)

    return decorated_function


# Routes
@app.route("/")
def landing():
    """Landing page"""
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please provide both username and password", "error")
            return render_template("login.html")

        user = db_manager.execute_query(
            "SELECT id, password_hash, rank, unit, clearance_level FROM users WHERE username = ?",
            (username,),
            fetch="one",
        )

        if user and check_password_hash(user[1], password):
            session.update(
                {
                    "user_id": user[0],
                    "username": username,
                    "rank": user[2],
                    "unit": user[3],
                    "clearance_level": user[4],
                    "session_id": str(uuid.uuid4()),
                }
            )

            # Update last login
            db_manager.execute_query(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user[0],),
            )

            flash("Login successful", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        rank = request.form.get("rank", "").strip()
        unit = request.form.get("unit", "").strip()

        if not all([username, password, rank, unit]):
            flash("All fields are required", "error")
            return render_template("register.html")

        try:
            password_hash = generate_password_hash(password)
            db_manager.execute_query(
                """
                INSERT INTO users (username, password_hash, rank, unit)
                VALUES (?, ?, ?, ?)
            """,
                (username, password_hash, rank, unit),
            )

            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                flash("Username already exists", "error")
            else:
                flash("Registration failed. Please try again.", "error")
                logger.error(f"Registration error: {e}")

    return render_template("register.html")


@app.route("/logout")
def logout():
    """User logout"""
    session_id = session.get("session_id")
    if session_id:
        chat_system = get_chat_system()
        chat_system.clear_session(session_id)

    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard"""
    chat_system = get_chat_system()

    # Get user stats
    query_count = (
        db_manager.execute_query(
            "SELECT COUNT(*) FROM query_logs WHERE user_id = ?",
            (session["user_id"],),
            fetch="one",
        )[0]
        if db_manager.execute_query(
            "SELECT COUNT(*) FROM query_logs WHERE user_id = ?",
            (session["user_id"],),
            fetch="one",
        )
        else 0
    )

    # Check document status
    session_id = session.get("session_id")
    has_documents = chat_system.has_documents(session_id)
    document_count = chat_system.get_document_count(session_id)

    return render_template(
        "dashboard.html",
        ollama_status=chat_system.check_ollama_connection(),
        query_count=query_count,
        has_documents=has_documents,
        document_count=document_count,
    )


@app.route("/admin")
@admin_required
def admin_panel():
    """Admin panel for system management"""
    # Get system stats
    total_users = db_manager.execute_query("SELECT COUNT(*) FROM users", fetch="one")[0]
    total_queries = db_manager.execute_query(
        "SELECT COUNT(*) FROM query_logs", fetch="one"
    )[0]

    # Get user stats with query counts
    user_stats = db_manager.execute_query(
        """
        SELECT u.id, u.username, u.rank, u.unit, u.clearance_level, u.last_login,
               COUNT(q.id) as query_count, u.created_at
        FROM users u
        LEFT JOIN query_logs q ON u.id = q.user_id
        GROUP BY u.id
        ORDER BY query_count DESC
    """,
        fetch="all",
    )

    # Get query distribution by user
    query_distribution = db_manager.execute_query(
        """
        SELECT u.username, COUNT(q.id) as query_count
        FROM users u
        LEFT JOIN query_logs q ON u.id = q.user_id
        GROUP BY u.id
        HAVING query_count > 0
        ORDER BY query_count DESC
    """,
        fetch="all",
    )

    # Get unit distribution
    unit_distribution = db_manager.execute_query(
        """
        SELECT unit, COUNT(*) as user_count
        FROM users
        GROUP BY unit
        ORDER BY user_count DESC
    """,
        fetch="all",
    )

    # Get rank distribution
    rank_distribution = db_manager.execute_query(
        """
        SELECT rank, COUNT(*) as user_count
        FROM users
        GROUP BY rank
        ORDER BY user_count DESC
    """,
        fetch="all",
    )

    return render_template(
        "admin.html",
        total_users=total_users,
        total_queries=total_queries,
        user_stats=user_stats or [],
        query_distribution=query_distribution or [],
        unit_distribution=unit_distribution or [],
        rank_distribution=rank_distribution or [],
    )


@app.route("/admin/user/<int:user_id>")
@admin_required
def get_user_details(user_id):
    """Get detailed user information"""
    # Get user info
    user_info = db_manager.execute_query(
        """
        SELECT username, rank, unit, clearance_level, created_at, last_login
        FROM users WHERE id = ?
    """,
        (user_id,),
        fetch="one",
    )

    if not user_info:
        return jsonify({"error": "User not found"}), 404

    # Get recent queries
    recent_queries = db_manager.execute_query(
        """
        SELECT query, timestamp, classification
        FROM query_logs
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT 100
    """,
        (user_id,),
        fetch="all",
    )

    # Get total query count
    total_queries = db_manager.execute_query(
        "SELECT COUNT(*) FROM query_logs WHERE user_id = ?", (user_id,), fetch="one"
    )[0]

    return jsonify(
        {
            "username": user_info[0],
            "rank": user_info[1],
            "unit": user_info[2],
            "clearance_level": user_info[3],
            "created_at": user_info[4],
            "last_login": user_info[5],
            "total_queries": total_queries,
            "recent_queries": [
                {
                    "query": q[0][:] + "..." if len(q[0]) > 100 else q[0],
                    "timestamp": q[1],
                    "classification": q[2],
                }
                for q in (recent_queries or [])
            ],
        }
    )


@app.route("/admin/delete-user/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    if user_id == session.get("user_id"):
        return (
            jsonify({"success": False, "message": "Cannot delete your own account"}),
            400,
        )

    try:
        # Delete user's query logs first
        db_manager.execute_query("DELETE FROM query_logs WHERE user_id = ?", (user_id,))

        # Delete user
        rows_deleted = db_manager.execute_query(
            "DELETE FROM users WHERE id = ?", (user_id,)
        )

        if rows_deleted == 0:
            return jsonify({"success": False, "message": "User not found"}), 404

        return jsonify({"success": True, "message": "User deleted successfully"})

    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return jsonify({"success": False, "message": "Error deleting user"}), 500


@app.route("/status")
def system_status():
    """System status check"""
    chat_system = get_chat_system()

    return jsonify(
        {
            "ollama": chat_system.check_ollama_connection(),
            "embeddings": chat_system.check_embedding_model(),
            "active_sessions": chat_system.get_active_sessions_count(),
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/export-report", methods=["POST"])
@login_required
def export_chat():
    """Export current chat session as PDF"""
    try:
        # Support both JSON and form-data
        if request.is_json:
            chat_history = request.get_json().get("chat_history", [])
        else:
            chat_history = json.loads(request.form.get("chat_history", "[]"))

        if not chat_history:
            return (
                jsonify({"success": False, "message": "No chat history provided"}),
                400,
            )

        # Create temporary PDF file
        temp_filename = f'chat_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        temp_pdf = os.path.join(app.config["TEMP_FOLDER"], temp_filename)

        # Build PDF
        doc = SimpleDocTemplate(temp_pdf, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=30
        )
        elements.append(Paragraph("Chat Export Report", title_style))
        elements.append(Spacer(1, 12))

        timestamp_style = ParagraphStyle(
            "Timestamp", parent=styles["Normal"], fontSize=10, textColor=colors.gray
        )
        elements.append(
            Paragraph(
                f"Generated on: {datetime.now():%Y-%m-%d %H:%M:%S}", timestamp_style
            )
        )
        elements.append(Spacer(1, 20))

        message_style = ParagraphStyle(
            "Message", parent=styles["Normal"], fontSize=11, spaceAfter=15
        )

        for message in chat_history:
            role_label = "User" if message.get("role") == "user" else "AI Assistant"
            elements.append(Paragraph(f"<b>{role_label}:</b>", message_style))
            elements.append(Paragraph(message.get("content", ""), message_style))
            elements.append(Spacer(1, 10))

            if "timestamp" in message:
                elements.append(
                    Paragraph(f"<i>Time: {message['timestamp']}</i>", timestamp_style)
                )
            if "metadata" in message and message["metadata"].get("sources"):
                elements.append(
                    Paragraph(
                        f"<i>Sources: {message['metadata']['sources']}</i>",
                        timestamp_style,
                    )
                )

            elements.append(Spacer(1, 15))

        doc.build(elements)

        return send_file(
            temp_pdf,
            as_attachment=True,
            download_name=temp_filename,
            mimetype="application/pdf",
        )

    except Exception as e:
        logger.error(f"Error exporting chat: {e}")
        return jsonify({"success": False, "message": "Failed to export chat"}), 500


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true",
        port=int(os.environ.get("PORT", 9000)),
        host=os.environ.get("HOST", "0.0.0.0"),
    )
