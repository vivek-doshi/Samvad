# Create admin user, prompt for password
# Note 1: This script is run ONCE during initial server setup to create the
# default administrator account. It interactively prompts for a password,
# hashes it with bcrypt via security/auth.py, and inserts the user row.
#
# Note 2: Why prompt for the password instead of using a default?
# Hard-coded default passwords (e.g. "admin123") are a top security risk —
# they are the first thing attackers try. Forcing interactive input ensures
# the admin always sets a real password before the server goes live.
#
# Note 3: Typical usage in a setup workflow:
#   cd project_root
#   python backend/db/seeds/seed_admin_user.py
#   > Enter username [admin]: admin
#   > Enter display name: Administrator
#   > Enter password (min 8 chars): ****
#   > Confirm password: ****
#   > Admin user created successfully.
#
# Note 4: After running this script, the admin can log in at /api/auth/login.
# Additional users can be added by inserting rows into the 'users' table
# or by building an admin UI for user management (a future enhancement).
