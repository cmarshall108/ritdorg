#!/usr/bin/env python3
"""Generate an ADMIN_PASS_HASH for the admin panel.

Usage:
    python set_admin_password.py
    python set_admin_password.py 'my new password'

Copy the printed hash into your environment as ADMIN_PASS_HASH.
"""

import getpass
import sys

from werkzeug.security import generate_password_hash


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("New admin password: ")
        confirm = getpass.getpass("Confirm: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)
    print()
    print("Add this to your environment (e.g. .env):")
    print()
    print(f"ADMIN_PASS_HASH='{generate_password_hash(password)}'")


if __name__ == "__main__":
    main()
