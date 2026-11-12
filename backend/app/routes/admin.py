"""Administrator dashboard, customer/account management and audit endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from mysql.connector import Error
from ..database import get_db
from ..dependencies import admin_user, require_admin
from ..schemas import CustomerCreate, AccountUpdate
from ..security import hash_secret
from ..routes.atm import money

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/dashboard")
def dashboard(user=Depends(admin_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS customers FROM customers")
    customers = cur.fetchone()["customers"]
    cur.execute("SELECT COUNT(*) AS accounts,COALESCE(SUM(status='active'),0) AS active_accounts FROM accounts")
    accounts = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS transactions,COALESCE(SUM(amount),0) AS volume FROM transactions WHERE status='success'")
    transactions = cur.fetchone()
    cur.close()
    return {"customers": customers, "accounts": accounts["accounts"],
            "active_accounts": int(accounts["active_accounts"]), "transactions": transactions["transactions"],
            "simulated_volume": money(transactions["volume"])}


@router.get("/customers")
def list_customers(user=Depends(admin_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT c.id,c.full_name,c.email,c.phone,c.status,c.created_at,COUNT(a.id) AS account_count
                    FROM customers c LEFT JOIN accounts a ON a.customer_id=c.id
                    GROUP BY c.id,c.full_name,c.email,c.phone,c.status,c.created_at ORDER BY c.id DESC""")
    rows = cur.fetchall()
    cur.close()
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    return {"customers": rows}


@router.post("/customers", status_code=201)
def create_customer(body: CustomerCreate, user=Depends(require_admin), conn=Depends(get_db)):
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO customers(full_name,email,phone) VALUES(%s,%s,%s)",
                    (body.full_name.strip(), str(body.email).lower(), body.phone.strip()))
        customer_id = cur.lastrowid
        cur.execute("""INSERT INTO accounts(account_number,customer_id,balance,daily_limit,transaction_limit)
                        VALUES(%s,%s,%s,%s,%s)""",
                    (body.account_number, customer_id, body.initial_balance, body.daily_limit, body.transaction_limit))
        account_id = cur.lastrowid
        cur.execute("INSERT INTO demo_credentials(account_id,pin_hash) VALUES(%s,%s)",
                    (account_id, hash_secret(body.pin)))
        cur.execute("INSERT INTO admin_audit(admin_user_id,action,target_type,target_id,reason) VALUES(%s,'CREATE_CUSTOMER','customer',%s,'Created demo customer and account')",
                    (int(user["sub"]), str(customer_id)))
        conn.commit()
        return {"message": "Demo customer and account created", "customer_id": customer_id, "account_id": account_id}
    except Error as exc:
        conn.rollback()
        if exc.errno == 1062:
            raise HTTPException(status_code=409, detail="Email or account number already exists")
        raise
    finally:
        cur.close()


@router.get("/accounts")
def list_accounts(user=Depends(admin_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT a.id,a.account_number,a.balance,a.currency,a.status,a.daily_limit,a.transaction_limit,
                    c.full_name,c.email FROM accounts a JOIN customers c ON c.id=a.customer_id ORDER BY a.id DESC""")
    rows = cur.fetchall()
    cur.close()
    for row in rows:
        for field in ("balance", "daily_limit", "transaction_limit"):
            row[field] = money(row[field])
    return {"accounts": rows}


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountUpdate, user=Depends(require_admin), conn=Depends(get_db)):
    changes, values = [], []
    if body.status is not None:
        changes.append("status=%s")
        values.append(body.status)
    if body.daily_limit is not None:
        changes.append("daily_limit=%s")
        values.append(body.daily_limit)
    if body.transaction_limit is not None:
        changes.append("transaction_limit=%s")
        values.append(body.transaction_limit)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one account field to update")
    cur = conn.cursor()
    values.append(account_id)
    cur.execute("UPDATE accounts SET " + ",".join(changes) + " WHERE id=%s", tuple(values))
    if cur.rowcount == 0:
        # MySQL reports zero changed rows when the requested values already match.
        cur.execute("SELECT id FROM accounts WHERE id=%s", (account_id,))
        exists = cur.fetchone()
        if not exists:
            cur.close()
            raise HTTPException(status_code=404, detail="Account not found")
        conn.rollback()
        cur.close()
        return {"message": "Account already has the requested values"}
    cur.execute("INSERT INTO admin_audit(admin_user_id,action,target_type,target_id,reason) VALUES(%s,'UPDATE_ACCOUNT','account',%s,'Updated account status or limits')",
                (int(user["sub"]), str(account_id)))
    conn.commit()
    cur.close()
    return {"message": "Account updated"}


@router.get("/transactions")
def search_transactions(user=Depends(admin_user), account_number: str = None,
                        txn_type: str = None, limit: int = Query(100, ge=1, le=500), conn=Depends(get_db)):
    allowed_types = {"deposit", "withdrawal", "transfer_in", "transfer_out", "adjustment"}
    if txn_type and txn_type not in allowed_types:
        raise HTTPException(status_code=422, detail="Invalid transaction type")
    sql = """SELECT t.transaction_reference,t.type,t.amount,t.status,t.description,t.balance_after,t.created_at,
             a.account_number,c.full_name FROM transactions t JOIN accounts a ON a.id=t.account_id
             JOIN customers c ON c.id=a.customer_id WHERE 1=1"""
    params = []
    if account_number:
        sql += " AND a.account_number=%s"
        params.append(account_number)
    if txn_type:
        sql += " AND t.type=%s"
        params.append(txn_type)
    sql += " ORDER BY t.created_at DESC,t.id DESC LIMIT %s"
    params.append(limit)
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    for row in rows:
        row["amount"] = money(row["amount"])
        row["balance_after"] = money(row["balance_after"])
        row["created_at"] = row["created_at"].isoformat()
    return {"transactions": rows}


@router.get("/audit")
def audit(user=Depends(admin_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT aa.id,au.email,aa.action,aa.target_type,aa.target_id,aa.reason,aa.created_at
                    FROM admin_audit aa JOIN admin_users au ON au.id=aa.admin_user_id
                    ORDER BY aa.created_at DESC LIMIT 200""")
    rows = cur.fetchall()
    cur.close()
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    return {"audit": rows}
