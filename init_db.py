"""
Database initialization script for Heroku deployment
Run with: heroku run python init_db.py
"""

from app import app, db
from models import init_default_data

def initialize_database():
    """Initialize database tables and default data"""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        
        print("Initializing default data...")
        init_default_data()
        
        print("✅ Database initialized successfully!")
        print("Default admin credentials:")
        print("  Username: admin")
        print("  Password: admin123")

if __name__ == "__main__":
    initialize_database()