# mauzenfan/server/services/auth_service.py
# This file will contain the business logic for user authentication.

def register_user(name, email, password, phone_number):
    # Validate input
    # Check if email already exists
    # Hash the password
    # Create and save the new user (using User model)
    pass

def login_user(email, password):
    # Find user by email
    # Verify password
    # Generate and return a session token (e.g., JWT)
    pass

def logout_user(session_token):
    # Invalidate the session token
    pass

def get_current_user(session_token):
    # Validate token and retrieve user details
    pass

def hash_password(password):
    # Logic to hash a password
    pass

def verify_password(plain_password, hashed_password):
    # Logic to verify a password against its hash
    pass
