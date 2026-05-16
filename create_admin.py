#!/usr/bin/env python3
"""
Script to create an admin user in the database
Run this script to create a proper admin user for testing
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def create_admin_user(email: str, password: str, full_name: str = None):
    """Create an admin user in the database"""
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"User {email} already exists with role: {existing_user.role.value}")
            if existing_user.role == UserRole.admin:
                print("User is already an admin!")
                return True
            else:
                # Update existing user to admin
                existing_user.role = UserRole.admin
                db.commit()
                print(f"Updated existing user {email} to admin role")
                return True
        
        # Create new admin user
        hashed_password = hash_password(password)
        admin_user = User(
            email=email,
            full_name=full_name or email.split('@')[0],
            hashed_password=hashed_password,
            role=UserRole.admin,
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        
        print(f"Successfully created admin user:")
        print(f"   Email: {email}")
        print(f"   Name: {admin_user.full_name}")
        print(f"   Role: {admin_user.role.value}")
        print(f"   ID: {admin_user.id}")
        return True
        
    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """Main function to run the admin creation"""
    print("Creating Admin User for Maverick Certification Hub")
    print("=" * 50)
    
    # Default admin credentials (you can change these)
    default_email = "admin@maverick.com"
    default_password = "admin123"
    default_name = "System Administrator"
    
    # Try to create admin with default credentials
    success = create_admin_user(default_email, default_password, default_name)
    
    if success:
        print("\nAdmin user created successfully!")
        print(f"Login with: {default_email}")
        print(f"Password: {default_password}")
        print(f"URL: http://localhost:5174")
        print("\nRemember to change the default password in production!")
    else:
        print("\nFailed to create admin user")
        sys.exit(1)


if __name__ == "__main__":
    main()
