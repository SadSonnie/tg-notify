#!/usr/bin/env python3
"""
Database setup script for PostgreSQL
Creates database and user if they don't exist
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_database():
    """Create database and user if they don't exist"""
    
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': 'postgres',  # Connect to default database first
        'user': 'postgres',      # Default superuser
        'password': input("Enter PostgreSQL superuser password: ")
    }
    
    target_db = os.getenv('DB_NAME', 'timetracker')
    target_user = os.getenv('DB_USER', 'timetracker_user')
    target_password = os.getenv('DB_PASSWORD', '')
    
    if not target_password:
        target_password = input(f"Enter password for user '{target_user}': ")
    
    try:
        # Connect to PostgreSQL
        print("Connecting to PostgreSQL...")
        conn = psycopg2.connect(**db_config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s",
            (target_user,)
        )
        
        if not cursor.fetchone():
            print(f"Creating user '{target_user}'...")
            cursor.execute(
                f"CREATE USER {target_user} WITH PASSWORD %s",
                (target_password,)
            )
            print(f"User '{target_user}' created successfully!")
        else:
            print(f"User '{target_user}' already exists.")
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (target_db,)
        )
        
        if not cursor.fetchone():
            print(f"Creating database '{target_db}'...")
            cursor.execute(f"CREATE DATABASE {target_db} OWNER {target_user}")
            print(f"Database '{target_db}' created successfully!")
        else:
            print(f"Database '{target_db}' already exists.")
        
        # Grant privileges
        cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {target_db} TO {target_user}")
        print(f"Privileges granted to '{target_user}' on database '{target_db}'.")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Database setup completed successfully!")
        print(f"Database: {target_db}")
        print(f"User: {target_user}")
        print(f"Host: {db_config['host']}")
        print(f"Port: {db_config['port']}")
        
        print("\nNext steps:")
        print("1. Copy .env.example to .env")
        print("2. Update .env with your bot token and admin user ID")
        print("3. Run: python bot.py")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print("🗄️  PostgreSQL Database Setup for Telegram Time Tracker")
    print("=" * 55)
    create_database()
