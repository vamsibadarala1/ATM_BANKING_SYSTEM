# ATM Banking Simulator (Learning Project)

A complete practice full-stack project: **React + Vite frontend**, **FastAPI backend**, and **MySQL through `mysql.connector`**. SQLAlchemy is not used.

> **Safety:** This is a fictional training simulator. It does not connect to a bank, process real money, communicate with an ATM, or dispense cash. Do not enter real banking credentials.

## Features included

### Customer
- Sign in with a fictional account number and demo PIN.
- PBKDF2-HMAC-SHA256 PIN hashing; failed-login counter and five-minute lock after three wrong PINs.
- View profile and available demo balance.
- Simulated deposit and withdrawal.
- Withdrawal notes must be multiples of ₹100.
- Per-transaction and daily debit limits; insufficient-balance checks.
- Transfer between fictional accounts. Sender debit and beneficiary credit are committed in one database transaction.
- Idempotency keys prevent the same submitted transaction request from being posted twice.
- Mini statement, beneficiary list, change demo PIN, logout/token revocation.

### Administrator
- Separate administrator login and role-protected endpoints.
- Dashboard counts and simulated transaction volume.
- Create and list customers, accounts, and transaction records.
- Change account status and transaction/daily limits.
- Audit records for account/customer administration.

## Project structure

```text
atm_banking_system/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── auth.py          # Login and logout
│   │   │   ├── atm.py           # Customer ATM operations
│   │   │   └── admin.py         # Admin operations
│   │   ├── config.py            # Environment configuration
│   │   ├── database.py          # mysql.connector connections
│   │   ├── dependencies.py      # JWT and role checks
│   │   ├── schemas.py            # Request validation
│   │   ├── security.py           # Hashing and JWT helpers
│   │   └── main.py               # FastAPI app and router registration
│   ├── database/schema.sql       # Database and tables
│   ├── tests/test_security.py    # Offline unit tests
│   ├── .env.example
│   ├── requirements.txt
│   └── seed_demo.py              # Demo accounts and administrator
├── frontend/
│   ├── src/App.jsx
│   ├── src/main.jsx
│   ├── src/style.css
│   └── package.json
├── docs/CODE_EXPLANATION.md
└── README.md
```

Every Python route module in `backend/app/routes/` contains working endpoints; `__init__.py` files are intentionally package markers and need not contain route logic.

## Requirements
- Python 3.9 or newer (Python 3.11/3.12 recommended)
- MySQL 8.0 or newer, with a local MySQL service running
- Node.js 18 or newer and npm
- VS Code or another editor

## 1. Extract the ZIP
Extract `atm_banking_system.zip` into Desktop. Your folder should be:
`~/Desktop/atm_banking_system`

## 2. Create the MySQL database
Open MySQL Workbench, connect to your local MySQL server, and run the complete script `backend/database/schema.sql`.

Or from Terminal, run this from the extracted project root:

```bash
mysql -u root -p < backend/database/schema.sql
```

Enter your MySQL password when prompted. This script creates `atm_practice` and its tables. It uses `CREATE TABLE IF NOT EXISTS`; it does not delete existing tables or user data.

## 3. Configure and start the backend
Open Terminal tab 1:

```bash
cd ~/Desktop/atm_banking_system/backend
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`. Set your actual local MySQL password in `DB_PASSWORD`. Replace `SECRET_KEY` with a private random value of at least 32 characters. For example, generate one with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `.env`. Keep `.env` private; never commit it to GitHub.

Still in the `backend` directory and with `(venv)` active:

```bash
python seed_demo.py
uvicorn app.main:app --reload
```

Expected backend URL: `http://127.0.0.1:8000`

- API health: http://127.0.0.1:8000/api/v1/health
- Interactive API docs: http://127.0.0.1:8000/docs

The health endpoint should return `api: ok` and `database: connected`.

## 4. Start the React frontend
Keep backend Terminal tab 1 running. Open Terminal tab 2:

```bash
cd ~/Desktop/atm_banking_system/frontend
npm install
cp .env.example .env
npm run dev
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173/`.

## Fictional demo credentials

| Role | Account / Email | PIN / Password |
|---|---|---|
| Customer 1 | `1000001234` | `1234` |
| Customer 2 | `1000005678` | `2345` |
| Customer 3 | `1000009012` | `3456` |
| Admin | `admin@atm-demo.local` | `Admin@12345` |

The seed script is repeatable: it skips demo accounts that already exist. If you change the admin environment credentials after the first seed, the existing administrator's password is not overwritten automatically.

## 5. Run the offline tests
From the backend directory with the virtual environment active:

```bash
pytest -q
```

These unit tests verify password/PIN hashing. They do not replace an end-to-end test against your own MySQL server.

## API route summary

All routes are under `/api/v1`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/atm/login` | Customer login |
| POST | `/admin/login` | Admin login |
| POST | `/atm/logout` | Revoke current token |
| GET | `/atm/me` | Customer profile |
| GET | `/atm/balance` | Balance enquiry |
| GET | `/atm/mini-statement` | Recent transactions |
| GET | `/atm/beneficiaries` | Other active demo accounts |
| POST | `/atm/deposit` | Simulated deposit |
| POST | `/atm/withdraw` | Simulated withdrawal |
| POST | `/atm/transfer` | Simulated account-to-account transfer |
| POST | `/atm/change-pin` | Change demo PIN |
| GET | `/admin/dashboard` | Admin summary |
| GET/POST | `/admin/customers` | List/create customers |
| GET | `/admin/accounts` | List accounts |
| PATCH | `/admin/accounts/{account_id}` | Update status/limits |
| GET | `/admin/transactions` | Search transaction history |
| GET | `/admin/audit` | View admin audit history |

## How the request flows

1. React sends an HTTP request using Axios.
2. FastAPI validates the JSON body with a Pydantic schema.
3. A dependency opens a MySQL connection and, for protected routes, verifies the JWT and role.
4. The route executes parameterized SQL through `mysql.connector`.
5. Money-changing routes lock the relevant account rows with `SELECT ... FOR UPDATE`.
6. Related balance and ledger writes commit together, or roll back together on an error.
7. FastAPI returns JSON; React refreshes the balance or table.

## Learning notes and limitations

- All balances and transfers are fictional. A deposit only updates the simulator's database; it does not accept cash.
- The simulator is a learning project, not production banking software. A real banking application needs security architecture review, HTTPS, robust rate limiting, secrets management, monitoring, backups, formal migrations, reconciliation, fraud controls, compliance review and extensive tests.
- The current admin UI focuses on dashboard, customer creation, account listing and transaction listing. The API also supports account status/limit updates and audit retrieval, which can be added to the UI as a next step.
- Daily debit limits are evaluated using the database server's `CURDATE()` timezone.
