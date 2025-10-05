import os
import logging
import re
import requests
import numpy as np
import json
import shutil
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify, session, current_app, send_file
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3
import uuid
from .doc_process import ChatSystem

# Configure logger
logger = logging.getLogger(__name__)

# Create Blueprint
chat_bp = Blueprint("chat", __name__, url_prefix="/")

# Global chat system instance
_chat_system = None


def login_required(f):
    """Decorator to require user authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            session["user_id"] = f"user_{uuid.uuid4().hex[:8]}"
        return f(*args, **kwargs)

    return decorated_function


def ensure_session_id():
    """Ensure session has a consistent session_id"""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def init_database():
    """Initialize database with enhanced schema for chat history"""
    try:
        os.makedirs("database", exist_ok=True)
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()

            # Enhanced sessions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_name TEXT,
                    pdf_filename TEXT,
                    pdf_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT
                )
            """
            )

            # Enhanced messages table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    response TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    page_references TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
                )
            """
            )

            # Session documents table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS session_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    document_name TEXT NOT NULL,
                    document_path TEXT NOT NULL,
                    document_hash TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
                )
            """
            )

            # Create indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_user ON chat_messages(user_id)"
            )

            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")


def create_new_session(user_id, pdf_filename=None):
    """Create a new chat session"""
    session_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    session_name = f"Session - {timestamp}"

    if pdf_filename:
        session_name = f"{pdf_filename} - {timestamp}"

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chat_sessions (id, user_id, session_name, pdf_filename)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, user_id, session_name, pdf_filename),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error creating session: {e}")

    return session_id


def save_message(session_id, user_id, sender, message, response=None, page_refs=None):
    """Save a message to the database"""
    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chat_messages 
                (session_id, user_id, sender, message, response, page_references)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    user_id,
                    sender,
                    message,
                    response,
                    json.dumps(page_refs) if page_refs else None,
                ),
            )

            # Update session last activity
            cursor.execute(
                """
                UPDATE chat_sessions 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """,
                (session_id,),
            )

            conn.commit()
    except Exception as e:
        logger.error(f"Error saving message: {e}")


def save_document_to_session(session_id, file_path, original_filename):
    """Save document reference to session and persist the file"""
    try:
        # Create persistent storage directory
        persist_dir = Path("persistent_documents") / session_id
        persist_dir.mkdir(parents=True, exist_ok=True)

        # Copy file to persistent location
        persistent_path = persist_dir / original_filename
        shutil.copy2(file_path, persistent_path)

        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()

            # Update session with PDF info
            cursor.execute(
                """
                UPDATE chat_sessions 
                SET pdf_filename = ?, pdf_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (original_filename, str(persistent_path), session_id),
            )

            # Add to session_documents
            cursor.execute(
                """
                INSERT INTO session_documents (session_id, document_name, document_path)
                VALUES (?, ?, ?)
            """,
                (session_id, original_filename, str(persistent_path)),
            )

            conn.commit()

        return str(persistent_path)
    except Exception as e:
        logger.error(f"Error saving document to session: {e}")
        return None


def get_chat_system():
    """Get or create chat system instance"""
    global _chat_system
    if _chat_system is None:
        _chat_system = ChatSystem(ollama_base_url="http://localhost:11434")
        init_database()  # Initialize database on first use
    return _chat_system


# Enhanced Routes


@chat_bp.route("/process-pdf", methods=["POST"])
@login_required
def process_pdf():
    """Handle PDF processing with session persistence"""
    chat_sys = get_chat_system()
    user_id = session.get("user_id")
    uploaded_files = []

    try:
        # Check if file was provided
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file selected"})

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "message": "No file selected"})

        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()

        # Check file type
        if file_ext not in {".pdf", ".docx", ".txt", ".doc"}:
            return jsonify(
                {
                    "success": False,
                    "message": "Unsupported file type. Please upload PDF, DOCX, TXT, or DOC files.",
                }
            )

        # Create new session
        session_id = create_new_session(user_id, filename)
        session["session_id"] = session_id

        # Save file temporarily
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{session_id}_{timestamp}_{filename}"
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_filename)

        file.save(file_path)
        uploaded_files.append(file_path)

        # Save document to persistent storage
        persistent_path = save_document_to_session(session_id, file_path, filename)

        # Process documents
        success, message = chat_sys.process_documents([file_path], session_id)

        if success:
            doc_count = chat_sys.get_document_count(session_id)

            # Save initial system message
            save_message(
                session_id,
                user_id,
                "system",
                f"Document '{filename}' uploaded and processed successfully.",
            )

            response = {
                "success": True,
                "message": message,
                "chunks": doc_count,
                "session_id": session_id,
                "filename": filename,
            }
        else:
            response = {"success": False, "message": message}

    except Exception as e:
        logger.error(f"Error processing file: {e}")
        response = {"success": False, "message": f"Error processing file: {str(e)}"}

    finally:
        # Cleanup temporary files
        for file_path in uploaded_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Error cleaning up file {file_path}: {e}")

    return jsonify(response)


@chat_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    """Handle chat messages with history persistence"""
    chat_sys = get_chat_system()
    session_id = ensure_session_id()
    user_id = session.get("user_id")

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"})

        query = data.get("message", "").strip()
        if not query:
            return jsonify({"success": False, "message": "Message cannot be empty"})

        if not chat_sys.has_documents(session_id):
            return jsonify(
                {
                    "success": False,
                    "message": "No documents uploaded. Please upload documents first.",
                }
            )

        # Generate answer
        result = chat_sys.generate_answer(query, session_id)

        if result["success"]:
            # Save message and response
            save_message(
                session_id,
                user_id,
                "user",
                query,
                result["answer"],
                result.get("page_references"),
            )

            return jsonify(
                {
                    "success": True,
                    "answer": result["answer"],
                    "sources": result.get("sources", ""),
                    "source_details": result.get("source_details", []),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "session_id": session_id,
                }
            )
        else:
            return jsonify({"success": False, "message": result["message"]})

    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        return jsonify(
            {
                "success": False,
                "message": "Error processing your question. Please try again.",
            }
        )


@chat_bp.route("/user-sessions", methods=["GET"])
@login_required
def get_user_sessions():
    """Get all sessions for the current user"""
    user_id = session.get("user_id")

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_name, pdf_filename, created_at, updated_at
                FROM chat_sessions
                WHERE user_id = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 50
            """,
                (user_id,),
            )

            sessions = []
            for row in cursor.fetchall():
                sessions.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "pdf_filename": row[2],
                        "created_at": row[3],
                        "updated_at": row[4],
                    }
                )

            return jsonify(
                {
                    "success": True,
                    "sessions": sessions,
                    "current_session": session.get("session_id"),
                }
            )
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return jsonify({"success": False, "message": "Error fetching sessions"})


@chat_bp.route("/session/<session_id>/messages", methods=["GET"])
@login_required
def get_session_messages(session_id):
    """Get all messages for a specific session"""
    user_id = session.get("user_id")

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()

            # Verify session belongs to user
            cursor.execute(
                """
                SELECT pdf_filename, pdf_path 
                FROM chat_sessions 
                WHERE id = ? AND user_id = ?
            """,
                (session_id, user_id),
            )

            session_info = cursor.fetchone()
            if not session_info:
                return jsonify({"success": False, "message": "Session not found"})

            # Get messages
            cursor.execute(
                """
                SELECT sender, message, response, timestamp, page_references
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """,
                (session_id,),
            )

            messages = []
            for row in cursor.fetchall():
                if row[0] == "user":
                    messages.append(
                        {"sender": "user", "content": row[1], "timestamp": row[3]}
                    )
                    if row[2]:  # Has response
                        messages.append(
                            {
                                "sender": "ai",
                                "content": row[2],
                                "timestamp": row[3],
                                "page_references": (
                                    json.loads(row[4]) if row[4] else None
                                ),
                            }
                        )

            return jsonify(
                {
                    "success": True,
                    "messages": messages,
                    "pdf_filename": session_info[0],
                    "pdf_path": session_info[1],
                }
            )
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({"success": False, "message": "Error fetching messages"})


@chat_bp.route("/load-session/<session_id>", methods=["POST"])
@login_required
def load_session(session_id):
    """Load a previous session with its document"""
    user_id = session.get("user_id")
    chat_sys = get_chat_system()

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()

            # Get session info
            cursor.execute(
                """
                SELECT pdf_path, pdf_filename
                FROM chat_sessions
                WHERE id = ? AND user_id = ?
            """,
                (session_id, user_id),
            )

            session_info = cursor.fetchone()
            if not session_info:
                return jsonify({"success": False, "message": "Session not found"})

            pdf_path, pdf_filename = session_info

            # Check if document exists
            if pdf_path and os.path.exists(pdf_path):
                # Re-process document for this session
                success, message = chat_sys.process_documents([pdf_path], session_id)

                if success:
                    session["session_id"] = session_id
                    return jsonify(
                        {
                            "success": True,
                            "message": "Session loaded successfully",
                            "pdf_filename": pdf_filename,
                            "session_id": session_id,
                        }
                    )
            else:
                return jsonify({"success": False, "message": "Document file not found"})

    except Exception as e:
        logger.error(f"Error loading session: {e}")
        return jsonify({"success": False, "message": "Error loading session"})


@chat_bp.route("/delete-session/<session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    """Soft delete a session"""
    user_id = session.get("user_id")

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()

            # Soft delete by marking as inactive
            cursor.execute(
                """
                UPDATE chat_sessions 
                SET is_active = 0 
                WHERE id = ? AND user_id = ?
            """,
                (session_id, user_id),
            )

            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({"success": True, "message": "Session deleted"})
            else:
                return jsonify({"success": False, "message": "Session not found"})

    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return jsonify({"success": False, "message": "Error deleting session"})


@chat_bp.route("/rename-session/<session_id>", methods=["PUT"])
@login_required
def rename_session(session_id):
    """Rename a session"""
    user_id = session.get("user_id")
    data = request.get_json()
    new_name = data.get("name", "").strip()

    if not new_name:
        return jsonify({"success": False, "message": "Name cannot be empty"})

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE chat_sessions 
                SET session_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            """,
                (new_name, session_id, user_id),
            )

            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({"success": True, "message": "Session renamed"})
            else:
                return jsonify({"success": False, "message": "Session not found"})

    except Exception as e:
        logger.error(f"Error renaming session: {e}")
        return jsonify({"success": False, "message": "Error renaming session"})


@chat_bp.route("/session/<session_id>/pdf", methods=["GET"])
@login_required
def get_session_pdf(session_id):
    """Get the PDF file for a session"""
    user_id = session.get("user_id")

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pdf_path, pdf_filename
                FROM chat_sessions
                WHERE id = ? AND user_id = ?
            """,
                (session_id, user_id),
            )

            result = cursor.fetchone()
            if result and result[0] and os.path.exists(result[0]):
                return send_file(
                    result[0],
                    as_attachment=False,
                    download_name=result[1],
                    mimetype="application/pdf",
                )
            else:
                return jsonify({"success": False, "message": "PDF not found"}), 404

    except Exception as e:
        logger.error(f"Error retrieving PDF: {e}")
        return jsonify({"success": False, "message": "Error retrieving PDF"}), 500


@chat_bp.route("/clear-all-sessions", methods=["DELETE"])
@login_required
def clear_all_sessions():
    """Clear all sessions for the current user"""
    user_id = session.get("user_id")

    try:
        with sqlite3.connect("database/military_docs.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE chat_sessions 
                SET is_active = 0 
                WHERE user_id = ?
            """,
                (user_id,),
            )
            conn.commit()

            # Clear current session
            session.pop("session_id", None)

            return jsonify({"success": True, "message": "All sessions cleared"})

    except Exception as e:
        logger.error(f"Error clearing sessions: {e}")
        return jsonify({"success": False, "message": "Error clearing sessions"})


# Keep existing routes for backward compatibility
@chat_bp.route("/chat-status")
@login_required
def chat_status():
    """Chat system status check"""
    chat_sys = get_chat_system()
    session_id = ensure_session_id()

    return jsonify(
        {
            "ollama": chat_sys.check_ollama_connection(),
            "embeddings": chat_sys.check_embedding_model(),
            "has_documents": chat_sys.has_documents(session_id),
            "document_count": chat_sys.get_document_count(session_id),
            "active_sessions": chat_sys.get_active_sessions_count(),
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }
    )


@chat_bp.route("/document-summary", methods=["GET"])
@login_required
def document_summary():
    """Return a smart welcome summary + suggested questions"""
    try:
        chat_sys = get_chat_system()
        session_id = ensure_session_id()

        if not chat_sys.has_documents(session_id):
            return jsonify(
                {"success": False, "message": "No documents available for summary"}
            )

        result = chat_sys.generate_smart_questions(session_id, count=5)

        return jsonify(
            {
                "success": True,
                "summary": result.get(
                    "welcome", "I've analyzed your document and I'm ready to help!"
                ),
                "questions": result.get("questions", []),
                "message": "Summary generated successfully",
            }
        )

    except Exception as e:
        logger.error(f"Error generating document summary: {e}")
        return jsonify({"success": False, "message": "Failed to generate summary"}), 500
