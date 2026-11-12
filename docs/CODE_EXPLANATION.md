# Code explanation – file by file

This guide explains what each source file is responsible for, why its important statements exist, and how the modules call one another. The Python source also includes comments beside important implementation decisions.

## 1. `backend/app/main.py` – application entry point

- `from fastapi import FastAPI, HTTPException`: imports the application class and the standard HTTP error type.
- `CORSMiddleware`: permits the browser frontend, running on port 5173, to call the backend on port 8000.
- `SECRET_KEY`: loaded from `.env`; it signs login tokens. Startup deliberately fails if it is shorter than 32 characters.
- `app = FastAPI(...)`: creates the API object and metadata shown in Swagger.
- `app.add_middleware(...)`: allows only the configured frontend origins and the HTTP methods/headers this application needs.
- `home()`: simple root endpoint used to confirm that the API process responds.
- `health()`: opens a real MySQL connection, runs `SELECT 1`, returns a success JSON response, and closes the connection in `finally`. A database problem becomes HTTP 503.
- `include_router(...)`: attaches the three route groups. `auth.py` owns login/logout; `atm.py` owns customer operations; `admin.py` owns administrator operations. The `/api/v1` prefix is applied consistently here.

## 2. `backend/app/config.py` – configuration

- `load_dotenv(...)` reads `backend/.env`; secrets and local passwords are kept out of source code.
- `DB_CONFIG` is a dictionary consumed by `mysql.connector.connect(**DB_CONFIG)`. `**` expands dictionary keys into keyword arguments.
- `SECRET_KEY` signs and verifies JWTs. It must be private and long.
- `ACCESS_TOKEN_MINUTES` controls how long a login token remains valid.
- `CORS_ORIGINS` splits the comma-separated frontend origins into a Python list.
- `ADMIN_EMAIL` and `ADMIN_PASSWORD` define the first demo admin credentials inserted by the seed script.

## 3. `backend/app/database.py` – MySQL connections

- `get_connection()` calls `mysql.connector.connect` using `DB_CONFIG` and returns a live connection.
- `get_db()` is a generator dependency. FastAPI runs the route with the yielded connection, then resumes the generator to close it.
- `rollback()` is called on a connector error so an unfinished transaction is not left pending.
- `finally` ensures the connection is closed even when a route raises an exception.
- Each route uses `conn.cursor()` for tuple rows or `conn.cursor(dictionary=True)` for dictionaries keyed by SQL column names.

## 4. `backend/app/schemas.py` – input validation

Pydantic models describe the JSON a route accepts. FastAPI validates the request before executing route logic.

- `CustomerLogin`: account number length and numeric PIN format are checked.
- `AdminLogin`: `EmailStr` validates email syntax; password length is bounded.
- `AmountRequest`: `Decimal` avoids binary floating-point currency calculations. `gt=0` rejects zero/negative amounts; `max_digits` and `decimal_places` constrain money precision. `idempotency_key` identifies one logical submission.
- `TransferRequest`: inherits amount and idempotency validation, then adds a beneficiary account number.
- `ChangePinRequest`: both PINs must contain 4–8 digits.
- `CustomerCreate`: validates customer data, account number, initial balance and configured limits.
- `AccountUpdate`: allows partial updates. `Optional` means the field may be omitted; the validator rejects unsupported account statuses.

## 5. `backend/app/security.py` – PIN/password and JWT security

- `hash_secret`: generates a random 16-byte salt, derives a SHA-256 PBKDF2 value with 310,000 iterations and stores the algorithm, iteration count, salt and digest. A random salt means equal PINs do not produce equal stored strings.
- `verify_secret`: parses the stored format, recalculates the PBKDF2 digest, and uses `hmac.compare_digest` to avoid ordinary early-exit string comparison.
- `create_token`: creates a unique token ID (`jti`), subject, role, issue time and expiry. JWT is signed with the configured secret.
- `decode_token`: verifies signature and expiry. A token is not accepted merely because it can be decoded.

## 6. `backend/app/dependencies.py` – route protection

- `current_user`: reads the `Authorization` header. It expects `Bearer <token>`, verifies the JWT, then checks `revoked_tokens` so a logged-out token cannot be reused.
- `customer_user`: allows only a token whose role is `customer`.
- `admin_user`: allows administrator and read-only auditor roles.
- `require_admin`: allows only the administrator role for actions that modify records.
- `Depends(...)` tells FastAPI to run the dependency before the endpoint and pass its returned value as an argument.

## 7. `backend/app/routes/auth.py` – authentication endpoints

### Customer login
1. The route receives a validated `CustomerLogin` object.
2. A parameterized SQL query joins accounts, customers and credential records. `%s` placeholders keep user values separate from SQL text.
3. `FOR UPDATE` locks the credential/account row while checking and updating failed attempts.
4. Inactive or unknown accounts are rejected with HTTP 401.
5. Three incorrect PINs cause a five-minute lock; a correct PIN resets the failed counter.
6. A successful login returns a signed JWT and a small profile object.

### Admin login
1. Finds the admin by normalized email.
2. Rejects missing, inactive or incorrectly authenticated admins.
3. Returns a role-bearing JWT and profile.

### Logout
1. Reads the authenticated token claims.
2. Converts token expiry into a MySQL datetime.
3. Stores its unique `jti` in `revoked_tokens`.
4. Future calls using that token fail in `current_user`.

## 8. `backend/app/routes/atm.py` – customer operations

- `router = APIRouter(prefix="/atm")` groups the customer routes. The main application adds `/api/v1`, so the final route is `/api/v1/atm/...`.
- `money(...)` formats a database Decimal to two decimal places for JSON.
- `/me` joins customer and account data to show the signed-in profile.
- `/balance` returns the current active account balance.
- `/mini-statement` selects only the signed-in account's recent transaction rows. The account ID comes from the verified token, not from an untrusted request parameter.
- `_post_single_transaction(...)` is the shared deposit/withdrawal engine:
  1. Check the idempotency key to reject repeated requests.
  2. Lock the account row using `FOR UPDATE`.
  3. Check active status and per-transaction limit.
  4. For debits, calculate the day's withdrawals/transfers and check daily limit and available balance.
  5. Calculate the new Decimal balance.
  6. Update the account and insert transaction plus ledger-entry records.
  7. Commit all writes together. Any exception triggers rollback.
- `/withdraw` additionally requires a multiple of ₹100 and invokes the shared transaction engine as a debit.
- `/deposit` invokes the same engine as a credit. It is a database simulation, not a cash deposit.
- `/beneficiaries` lists other active fictional accounts, never the signed-in account.
- `/transfer` locks both accounts in ascending ID order, validates both accounts, checks transaction/daily limits and available balance, updates both balances, writes transfer and ledger records, then commits once. If any step fails, both sides roll back.
- `/change-pin` verifies the old PIN, hashes the new PIN, clears failed-login lock fields and saves the new hash.

## 9. `backend/app/routes/admin.py` – administrator operations

- Every endpoint depends on `admin_user` or `require_admin`; customers cannot call admin endpoints.
- `/dashboard` uses SQL aggregate functions such as `COUNT` and `SUM` to build dashboard figures.
- `GET /customers` uses `LEFT JOIN` so customers are included even if no account is associated, and counts linked accounts.
- `POST /customers` inserts customer, account, hashed PIN and audit record in one transaction. A duplicate unique email/account becomes HTTP 409.
- `GET /accounts` joins account and customer details.
- `PATCH /accounts/{id}` builds only the SQL assignments for fields supplied by the admin. Values remain parameterized; only fixed, server-authored column fragments are concatenated.
- `/transactions` optionally filters by account number and transaction type; the limit is bounded from 1 to 500.
- `/audit` joins audit events to administrator email addresses.

## 10. `backend/seed_demo.py` – initial demo data

- `DEMO_CUSTOMERS` is the list of fictional customer rows.
- `seed()` opens one connection and starts a transaction.
- It inserts the demo admin only if the configured email is not already present.
- For each customer it checks the account number first, so running the script repeatedly does not duplicate the same demo account.
- It hashes PINs before inserting them into `demo_credentials`.
- `commit()` saves the complete seed set; `rollback()` undoes partial writes on failure.
- The `if __name__ == "__main__"` guard means the function runs only when the file is executed directly.

## 11. `backend/database/schema.sql` – relational structure

- `customers` stores customer identity/contact details.
- `accounts` belongs to one customer (`accounts.customer_id -> customers.id`) and stores the current demo balance and limits.
- `demo_credentials` stores one hashed PIN per account.
- `transactions` stores the account-facing transaction history; its unique idempotency key prevents duplicate request keys.
- `transfers` records the relationship between sender and beneficiary accounts.
- `transaction_entries` stores debit/credit ledger entries linked to a transaction and account.
- `admin_users` stores administrator identities and hashed passwords.
- `admin_audit` records administrator changes.
- `revoked_tokens` stores logged-out JWT IDs until expiry.
- `DECIMAL(12,2)` is used for money; `FLOAT`/`DOUBLE` are avoided for currency.
- InnoDB and foreign keys enforce relational integrity and support row-level locking/transactions.

## 12. `frontend/src/main.jsx`, `App.jsx` and `style.css`

- `main.jsx` imports React, the root `App` component and global stylesheet, then mounts the component into the HTML element with ID `root`.
- `App.jsx` creates an Axios client whose base URL points to FastAPI. An Axios request interceptor attaches the token from `sessionStorage` to protected requests.
- React state (`useState`) stores the selected mode, login token, profile, balance, transactions, selected page and error/success messages.
- The login handler posts credentials to the matching customer/admin endpoint and stores the returned access token for the browser session.
- The transaction helper posts the amount and a fresh idempotency key, then reloads the balance and mini statement.
- Customer panels call profile, balance, beneficiary, statement, transfer and PIN endpoints.
- The admin component calls dashboard/customer/account/transaction endpoints and sends customer creation data.
- `style.css` contains the responsive visual design; it does not contain business logic.

## 13. What happens during a withdrawal? (end-to-end example)

1. Customer enters an amount in React and confirms it.
2. React sends `POST /api/v1/atm/withdraw` with a JSON amount and idempotency key, and the Axios interceptor adds the JWT.
3. FastAPI parses the JSON into `AmountRequest`; invalid amount/precision/key is rejected before the route runs.
4. `customer_user` verifies the JWT, revocation status and customer role.
5. `get_db` supplies a MySQL connection.
6. The route checks the ₹100 multiple rule.
7. The shared transaction function checks duplicate submission, locks the account row, checks status, limits and balance.
8. It updates balance and inserts transaction/ledger rows in one commit.
9. FastAPI returns JSON with a reference and new demo balance.
10. React refreshes the balance and statement.

## Important distinction

The project is structured and statically checked for this learning environment, but a real local integration run still depends on your MySQL service, database password, `.env`, Python packages and Node/npm installation. Always verify `/api/v1/health`, Swagger and the browser workflow on your Mac. This project is not certified for real banking use.
