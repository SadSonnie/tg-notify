"""
Database configuration and connection management for PostgreSQL
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'timetracker'),
            'user': os.getenv('DB_USER', 'timetracker_user'),
            'password': os.getenv('DB_PASSWORD', '')
        }
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def get_cursor(self, dict_cursor=True):
        """Get database cursor with context manager"""
        with self.get_connection() as conn:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database cursor error: {e}")
                raise
            finally:
                cursor.close()
    
    def init_database(self):
        """Initialize database with required tables"""
        try:
            with self.get_cursor(dict_cursor=False) as cursor:
                # Users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        is_admin BOOLEAN DEFAULT FALSE,
                        is_banned BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Add is_banned column if it doesn't exist (for existing databases)
                cursor.execute('''
                    DO $$
                    BEGIN
                        BEGIN
                            ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;
                        EXCEPTION
                            WHEN duplicate_column THEN 
                            -- Column already exists, do nothing
                        END;
                    END $$;
                ''')
                
                # Projects table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) UNIQUE NOT NULL,
                        description TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Time entries table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS time_entries (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        project_id INTEGER REFERENCES projects(id),
                        hours DECIMAL(5,2) NOT NULL,
                        description TEXT,
                        date DATE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_time_entries_user_id 
                    ON time_entries(user_id)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_time_entries_date 
                    ON time_entries(date)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_time_entries_project_id 
                    ON time_entries(project_id)
                ''')
                
                # Insert default projects if none exist
                cursor.execute('SELECT COUNT(*) FROM projects')
                if cursor.fetchone()[0] == 0:
                    default_projects = [
                        ('Разработка', 'Основная разработка продукта'),
                        ('Тестирование', 'Тестирование и QA'),
                        ('Документация', 'Создание и обновление документации'),
                        ('Встречи', 'Совещания и планерки'),
                        ('Обучение', 'Изучение новых технологий')
                    ]
                    cursor.executemany(
                        'INSERT INTO projects (name, description) VALUES (%s, %s)',
                        default_projects
                    )
                
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def test_connection(self):
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    result = cursor.fetchone()
                    return result[0] == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

# Global database manager instance
db_manager = DatabaseManager()
