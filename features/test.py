#!/usr/bin/env python3
"""
Simple script to populate database with test sessions for debugging
This will add visible sessions to your chat history
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import random


def populate_test_data():
    """Add test sessions to make history visible"""

    # Create directories if they don't exist
    Path("database").mkdir(exist_ok=True)
    Path("persistent_documents").mkdir(exist_ok=True)

    db_path = Path("database") / "military_docs.db"

    print("Adding test sessions to database...")

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # First ensure tables exist with correct schema
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
                is_active INTEGER DEFAULT 1,
                metadata TEXT
            )
        """
        )

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

        # Test users
        users = ["demo_user", "user_123abc", "admin", "test_user"]

        # PDF filenames
        pdf_files = [
            "Annual_Report_2024.pdf",
            "Technical_Documentation.pdf",
            "Project_Proposal.pdf",
            "Research_Paper.pdf",
            "User_Manual.pdf",
            "Financial_Statement.pdf",
            "Meeting_Minutes.pdf",
            "Contract_Agreement.pdf",
        ]

        # Sample messages
        sample_questions = [
            "What are the key findings in this document?",
            "Can you summarize the main points?",
            "What is the total budget mentioned?",
            "Who are the stakeholders involved?",
            "What are the recommendations?",
            "What is the timeline for this project?",
            "Are there any risks mentioned?",
            "What are the success metrics?",
        ]

        sample_responses = [
            "Based on the document, the key findings include improved efficiency by 25% and cost reduction of $2.3 million.",
            "The main points are: 1) Implementation of new system, 2) Training requirements, 3) Budget allocation",
            "The total budget mentioned is $5.7 million for the fiscal year 2024.",
            "The primary stakeholders include the executive team, department heads, and external consultants.",
            "The document recommends proceeding with Phase 2 implementation by Q3 2024.",
            "The timeline spans 18 months with major milestones in Q2 and Q4.",
            "Yes, several risks are identified including technical challenges and resource constraints.",
            "Success metrics include ROI of 150%, user adoption rate of 80%, and system uptime of 99.9%.",
        ]

        sessions_created = 0

        for user in users:
            # Create 2-4 sessions per user
            num_sessions = random.randint(2, 4)

            for i in range(num_sessions):
                session_id = str(uuid.uuid4())
                pdf_file = random.choice(pdf_files)

                # Create timestamps for different days
                days_ago = random.randint(0, 30)
                created_at = datetime.now() - timedelta(
                    days=days_ago, hours=random.randint(0, 23)
                )
                updated_at = created_at + timedelta(minutes=random.randint(5, 120))

                session_name = f"{pdf_file.replace('.pdf', '')} - {created_at.strftime('%Y-%m-%d %H:%M')}"

                # Insert session
                cursor.execute(
                    """
                    INSERT INTO chat_sessions 
                    (id, user_id, session_name, pdf_filename, pdf_path, created_at, updated_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                    (
                        session_id,
                        user,
                        session_name,
                        pdf_file,
                        f"persistent_documents/{session_id}/{pdf_file}",
                        created_at.isoformat(),
                        updated_at.isoformat(),
                    ),
                )

                # Add 2-5 messages per session
                num_messages = random.randint(2, 5)
                for j in range(num_messages):
                    msg_time = created_at + timedelta(minutes=j * 5)
                    question = random.choice(sample_questions)
                    response = random.choice(sample_responses)

                    cursor.execute(
                        """
                        INSERT INTO chat_messages
                        (session_id, user_id, sender, message, response, timestamp)
                        VALUES (?, ?, 'user', ?, ?, ?)
                    """,
                        (session_id, user, question, response, msg_time.isoformat()),
                    )

                sessions_created += 1
                print(f"✓ Created session: {session_name[:50]}... for {user}")

        conn.commit()
        conn.close()

        print(f"\n✅ Successfully created {sessions_created} test sessions!")
        print("\nNow you should see sessions in your chat history sidebar:")
        print("  - Sessions are grouped by user")
        print("  - Each session has messages")
        print("  - Sessions span different dates")
        print("\n⚠️  Note: You'll see sessions for your current user_id")
        print("    (check your browser session/cookies for your user_id)")

        return True

    except Exception as e:
        print(f"\n❌ Error creating test data: {e}")
        import traceback

        traceback.print_exc()
        return False


def clear_all_sessions():
    """Clear all sessions from database"""
    db_path = Path("database") / "military_docs.db"

    if not db_path.exists():
        print("No database found.")
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("DELETE FROM chat_messages")
        cursor.execute("DELETE FROM chat_sessions")
        cursor.execute("DELETE FROM session_documents")

        conn.commit()
        conn.close()

        print("✅ Cleared all sessions from database")

    except Exception as e:
        print(f"❌ Error clearing sessions: {e}")


def show_current_stats():
    """Show current database statistics"""
    db_path = Path("database") / "military_docs.db"

    if not db_path.exists():
        print("No database found.")
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print("\n" + "=" * 60)
        print("CURRENT DATABASE STATISTICS")
        print("=" * 60)

        # Count by user
        cursor.execute(
            """
            SELECT user_id, COUNT(*) as session_count
            FROM chat_sessions
            WHERE is_active = 1
            GROUP BY user_id
            ORDER BY session_count DESC
        """
        )

        user_stats = cursor.fetchall()

        if user_stats:
            print("\nSessions by user:")
            for user, count in user_stats:
                print(f"  {user}: {count} sessions")
        else:
            print("\nNo active sessions found.")

        # Recent sessions
        cursor.execute(
            """
            SELECT session_name, user_id, created_at
            FROM chat_sessions
            WHERE is_active = 1
            ORDER BY created_at DESC
            LIMIT 5
        """
        )

        recent = cursor.fetchall()

        if recent:
            print("\nMost recent sessions:")
            for session in recent:
                print(f"  - {session[0][:40]}...")
                print(f"    User: {session[1]}, Created: {session[2]}")

        conn.close()

    except Exception as e:
        print(f"Error showing stats: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("CHAT HISTORY TEST DATA GENERATOR")
    print("=" * 60)

    # Show current stats
    show_current_stats()

    print("\nOptions:")
    print("1. Add test sessions")
    print("2. Clear all sessions")
    print("3. Exit")

    choice = input("\nEnter choice (1-3): ")

    if choice == "1":
        populate_test_data()
        show_current_stats()
    elif choice == "2":
        confirm = input("Are you sure you want to clear all sessions? (y/n): ")
        if confirm.lower() == "y":
            clear_all_sessions()
            show_current_stats()
    else:
        print("Exiting...")
