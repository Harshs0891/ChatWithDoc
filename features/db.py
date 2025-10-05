#!/usr/bin/env python3
"""
Diagnostic script to check why chat history isn't showing
Run this to see what's in your database and identify issues
"""

import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime


def check_database():
    """Check database structure and contents"""
    db_path = Path("database") / "military_docs.db"

    print("=" * 60)
    print("DATABASE DIAGNOSTIC REPORT")
    print("=" * 60)
    print(f"\n1. Database Location: {db_path.absolute()}")
    print(f"   Exists: {db_path.exists()}")

    if not db_path.exists():
        print("\n❌ Database doesn't exist! Run init_database.py first.")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check tables
        print("\n2. Database Tables:")
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()

        if not tables:
            print("   ❌ No tables found! Database is empty.")
            return False

        for table in tables:
            print(f"   ✓ {table[0]}")

        # Check chat_sessions structure
        print("\n3. chat_sessions Table Structure:")
        cursor.execute("PRAGMA table_info(chat_sessions)")
        columns = cursor.fetchall()

        required_columns = [
            "id",
            "user_id",
            "session_name",
            "pdf_filename",
            "is_active",
        ]
        found_columns = [col[1] for col in columns]

        for req_col in required_columns:
            if req_col in found_columns:
                print(f"   ✓ {req_col} column exists")
            else:
                print(f"   ❌ {req_col} column MISSING!")

        # Check chat_messages structure
        print("\n4. chat_messages Table Structure:")
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()

        required_columns = ["session_id", "user_id", "sender", "message", "response"]
        found_columns = [col[1] for col in columns]

        for req_col in required_columns:
            if req_col in found_columns:
                print(f"   ✓ {req_col} column exists")
            else:
                print(f"   ❌ {req_col} column MISSING!")

        # Check data
        print("\n5. Data Check:")

        # Count sessions
        cursor.execute("SELECT COUNT(*) FROM chat_sessions")
        total_sessions = cursor.fetchone()[0]
        print(f"   Total sessions: {total_sessions}")

        cursor.execute("SELECT COUNT(*) FROM chat_sessions WHERE is_active = 1")
        active_sessions = cursor.fetchone()[0]
        print(f"   Active sessions: {active_sessions}")

        # Count messages
        cursor.execute("SELECT COUNT(*) FROM chat_messages")
        total_messages = cursor.fetchone()[0]
        print(f"   Total messages: {total_messages}")

        # Show recent sessions
        if active_sessions > 0:
            print("\n6. Recent Active Sessions:")
            cursor.execute(
                """
                SELECT id, user_id, session_name, pdf_filename, created_at
                FROM chat_sessions 
                WHERE is_active = 1 
                ORDER BY updated_at DESC 
                LIMIT 5
            """
            )

            sessions = cursor.fetchall()
            for session in sessions:
                print(f"\n   Session ID: {session[0][:8]}...")
                print(f"   User: {session[1]}")
                print(f"   Name: {session[2]}")
                print(f"   PDF: {session[3]}")
                print(f"   Created: {session[4]}")

                # Count messages for this session
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM chat_messages 
                    WHERE session_id = ?
                """,
                    (session[0],),
                )
                msg_count = cursor.fetchone()[0]
                print(f"   Messages: {msg_count}")

        # Check for common issues
        print("\n7. Common Issues Check:")

        # Check if is_active column is INTEGER or BOOLEAN
        cursor.execute("PRAGMA table_info(chat_sessions)")
        columns = cursor.fetchall()
        for col in columns:
            if col[1] == "is_active":
                print(f"   is_active column type: {col[2]}")
                if col[2] not in ["INTEGER", "BOOLEAN"]:
                    print(f"   ⚠️  is_active should be INTEGER, not {col[2]}")

        # Check for orphaned messages
        cursor.execute(
            """
            SELECT COUNT(*) FROM chat_messages 
            WHERE session_id NOT IN (SELECT id FROM chat_sessions)
        """
        )
        orphaned = cursor.fetchone()[0]
        if orphaned > 0:
            print(f"   ⚠️  Found {orphaned} orphaned messages")
        else:
            print(f"   ✓ No orphaned messages")

        conn.close()

        print("\n" + "=" * 60)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Error during diagnostic: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_create_session():
    """Test creating a new session"""
    print("\n" + "=" * 60)
    print("TESTING SESSION CREATION")
    print("=" * 60)

    db_path = Path("database") / "military_docs.db"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create test session
        import uuid

        test_session_id = str(uuid.uuid4())
        test_user_id = "test_user_123"
        test_session_name = (
            f"Test Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        print(f"\nCreating test session:")
        print(f"  ID: {test_session_id[:8]}...")
        print(f"  User: {test_user_id}")
        print(f"  Name: {test_session_name}")

        cursor.execute(
            """
            INSERT INTO chat_sessions (id, user_id, session_name, pdf_filename, is_active)
            VALUES (?, ?, ?, ?, 1)
        """,
            (test_session_id, test_user_id, test_session_name, "test.pdf"),
        )

        # Create test message
        cursor.execute(
            """
            INSERT INTO chat_messages (session_id, user_id, sender, message, response)
            VALUES (?, ?, ?, ?, ?)
        """,
            (test_session_id, test_user_id, "user", "Test message", "Test response"),
        )

        conn.commit()

        # Verify it was created
        cursor.execute("SELECT * FROM chat_sessions WHERE id = ?", (test_session_id,))
        result = cursor.fetchone()

        if result:
            print("\n✓ Test session created successfully!")
            print("  You should now see this session in your chat history")
        else:
            print("\n❌ Failed to create test session")

        conn.close()
        return True

    except Exception as e:
        print(f"\n❌ Error creating test session: {e}")
        import traceback

        traceback.print_exc()
        return False


def fix_database_schema():
    """Attempt to fix common schema issues"""
    print("\n" + "=" * 60)
    print("ATTEMPTING TO FIX DATABASE SCHEMA")
    print("=" * 60)

    db_path = Path("database") / "military_docs.db"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Backup existing data
        print("\n1. Backing up existing data...")

        # Check if tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'"
        )
        if cursor.fetchone():
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS chat_sessions_backup AS SELECT * FROM chat_sessions"
            )
            print("   ✓ Backed up chat_sessions")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'"
        )
        if cursor.fetchone():
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS chat_messages_backup AS SELECT * FROM chat_messages"
            )
            print("   ✓ Backed up chat_messages")

        # Drop and recreate tables with correct schema
        print("\n2. Recreating tables with correct schema...")

        cursor.execute("DROP TABLE IF EXISTS chat_sessions")
        cursor.execute("DROP TABLE IF EXISTS chat_messages")
        cursor.execute("DROP TABLE IF EXISTS session_documents")

        # Create with correct schema
        cursor.execute(
            """
            CREATE TABLE chat_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_name TEXT,
                pdf_filename TEXT,
                pdf_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                metadata TEXT
            )
        """
        )
        print("   ✓ Created chat_sessions with correct schema")

        cursor.execute(
            """
            CREATE TABLE chat_messages (
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
        print("   ✓ Created chat_messages with correct schema")

        cursor.execute(
            """
            CREATE TABLE session_documents (
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
        print("   ✓ Created session_documents")

        # Create indexes
        cursor.execute("CREATE INDEX idx_sessions_user ON chat_sessions(user_id)")
        cursor.execute("CREATE INDEX idx_sessions_active ON chat_sessions(is_active)")
        cursor.execute("CREATE INDEX idx_messages_session ON chat_messages(session_id)")
        cursor.execute("CREATE INDEX idx_messages_user ON chat_messages(user_id)")
        print("   ✓ Created indexes")

        conn.commit()
        conn.close()

        print("\n✅ Schema fixed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Error fixing schema: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run diagnostic
    if check_database():
        print("\n✅ Database structure looks good!")
    else:
        print("\n⚠️  Database has issues!")

        # Ask to fix
        response = input("\nDo you want to fix the database schema? (y/n): ")
        if response.lower() == "y":
            if fix_database_schema():
                print("\n✅ Database fixed! Please restart your application.")
            else:
                print("\n❌ Failed to fix database.")

        # Ask to create test session
        response = input("\nDo you want to create a test session? (y/n): ")
        if response.lower() == "y":
            test_create_session()
            print("\nTest session created. Check your chat history sidebar!")
