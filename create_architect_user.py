"""
create_architect_user.py
CLI helper to seed architect / admin users.
Run once:  python create_architect_user.py
"""
import getpass
import sys

import architect_db
from auth import hash_password

architect_db.init_phase2_db()


def main():
    print("\n" + "=" * 55)
    print("  SHAMEER ASSOCIATES — Create Architect / Admin User")
    print("=" * 55 + "\n")

    email = input("Email address: ").strip().lower()
    if not email or '@' not in email:
        print("Invalid email address.")
        sys.exit(1)

    existing = architect_db.get_user_by_email(email)
    if existing:
        print(f"A user with email '{email}' already exists.")
        sys.exit(1)

    full_name = input("Full name: ").strip()
    if not full_name:
        print("Full name is required.")
        sys.exit(1)

    role_input = input("Role (architect/admin) [architect]: ").strip().lower()
    role = role_input if role_input in ('architect', 'admin') else 'architect'

    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    password_hash = hash_password(password)
    user_id = architect_db.create_user(email, password_hash, full_name, role)

    print(f"\n✓ User created successfully!")
    print(f"  Name  : {full_name}")
    print(f"  Email : {email}")
    print(f"  Role  : {role}")
    print(f"  ID    : {user_id}")
    print(f"\nAccess the architect workspace at: http://localhost:5000/architect\n")


if __name__ == '__main__':
    main()
