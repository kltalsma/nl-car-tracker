#!/usr/bin/env python3
"""
Migration script to create users table and initialize admin users
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import Database, User, Base
from werkzeug.security import generate_password_hash
from datetime import datetime

def create_users_table():
    """Create users table and initialize admin users"""
    # Initialize database
    db = Database('data/cars.db')
    
    # Create users table
    print("Creating users table...")
    Base.metadata.create_all(db.engine, tables=[User.__table__])
    print("✓ Users table created")
    
    # Create initial admin users
    session = db.get_session()
    
    try:
        # Check if users already exist
        existing_users = session.query(User).count()
        
        if existing_users == 0:
            print("\nCreating initial admin users...")
            
            # Create admin users from env vars (fallback to defaults for dev)
            admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin')
            admin = User(
                username=admin_username,
                password_hash=generate_password_hash(admin_password),
                is_admin=True,
                created_at=datetime.utcnow(),
                is_active=True
            )
            session.add(admin)
            print(f"✓ Created admin user: {admin_username}")
            
            session.commit()
            print("\n✓ Initial users created successfully!")
        else:
            print(f"\n⚠ Users table already has {existing_users} user(s). Skipping initialization.")
            
    except Exception as e:
        session.rollback()
        print(f"\n✗ Error creating users: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    create_users_table()
