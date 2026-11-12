"""Insert repeatable fictional demo accounts and the demo administrator."""
from app.database import get_connection
from app.security import hash_secret
from app.config import ADMIN_EMAIL, ADMIN_PASSWORD

DEMO_CUSTOMERS = [
    ("Aarav Sharma", "aarav.demo@example.test", "9000000001", "1000001234", "25000.00", "1234"),
    ("Priya Reddy", "priya.demo@example.test", "9000000002", "1000005678", "18000.00", "2345"),
    ("Rahul Kumar", "rahul.demo@example.test", "9000000003", "1000009012", "32000.00", "3456"),
]


def seed():
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT id FROM admin_users WHERE email=%s", (ADMIN_EMAIL,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO admin_users(full_name,email,password_hash,role) VALUES(%s,%s,%s,'admin')",
                           ("Demo Administrator", ADMIN_EMAIL, hash_secret(ADMIN_PASSWORD)))
        for name, email, phone, account_number, balance, pin in DEMO_CUSTOMERS:
            cursor.execute("SELECT id FROM accounts WHERE account_number=%s", (account_number,))
            if cursor.fetchone() is not None:
                continue  # Makes this seed script safe to run more than once.
            cursor.execute("INSERT INTO customers(full_name,email,phone) VALUES(%s,%s,%s)", (name, email, phone))
            customer_id = cursor.lastrowid
            cursor.execute("INSERT INTO accounts(account_number,customer_id,balance) VALUES(%s,%s,%s)",
                           (account_number, customer_id, balance))
            account_id = cursor.lastrowid
            cursor.execute("INSERT INTO demo_credentials(account_id,pin_hash) VALUES(%s,%s)",
                           (account_id, hash_secret(pin)))
        connection.commit()
        print("Demo data created or already present.")
        print("Customer 1: 1000001234 / 1234")
        print("Customer 2: 1000005678 / 2345")
        print("Customer 3: 1000009012 / 3456")
        print("Admin: {} / {}".format(ADMIN_EMAIL, ADMIN_PASSWORD))
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    seed()
