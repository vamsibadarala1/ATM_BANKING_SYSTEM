"""Customer ATM endpoints and atomic simulated money movements."""
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from mysql.connector import Error
from ..database import get_db
from ..dependencies import customer_user
from ..schemas import AmountRequest, TransferRequest, ChangePinRequest
from ..security import verify_secret, hash_secret

router = APIRouter(prefix="/atm", tags=["Customer ATM"])


def money(value):
    return str(Decimal(value).quantize(Decimal("0.01")))


@router.get("/me")
def profile(user=Depends(customer_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT c.full_name,a.account_number,a.balance,a.currency,a.status
                    FROM accounts a JOIN customers c ON c.id=a.customer_id WHERE a.id=%s""",
                (user["account_id"],))
    row = cur.fetchone()
    cur.close()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    row["balance"] = money(row["balance"])
    return row


@router.get("/balance")
def balance(user=Depends(customer_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT balance,currency,account_number,status FROM accounts WHERE id=%s", (user["account_id"],))
    row = cur.fetchone()
    cur.close()
    if not row or row["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    row["balance"] = money(row["balance"])
    row["simulation_only"] = True
    return row


@router.get("/mini-statement")
def mini_statement(limit: int = Query(10, ge=1, le=50), user=Depends(customer_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT transaction_reference,type,amount,status,description,balance_after,created_at
                    FROM transactions WHERE account_id=%s ORDER BY created_at DESC,id DESC LIMIT %s""",
                (user["account_id"], limit))
    rows = cur.fetchall()
    cur.close()
    for row in rows:
        row["amount"] = money(row["amount"])
        row["balance_after"] = money(row["balance_after"])
        row["created_at"] = row["created_at"].isoformat()
    return {"transactions": rows}


def _post_single_transaction(conn, account_id, amount, kind, description, key, debit=False):
    """Lock account, validate limits/balance, write ledger rows, and commit once."""
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id FROM transactions WHERE idempotency_key=%s", (key,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Duplicate request: this request was already processed")
        cur.execute("SELECT balance,status,daily_limit,transaction_limit FROM accounts WHERE id=%s FOR UPDATE",
                    (account_id,))
        account = cur.fetchone()
        if not account or account["status"] != "active":
            raise HTTPException(status_code=403, detail="Account is not active")
        if amount > Decimal(account["transaction_limit"]):
            raise HTTPException(status_code=422, detail="Per-transaction limit exceeded")
        current = Decimal(account["balance"])
        if debit:
            cur.execute("""SELECT COALESCE(SUM(amount),0) AS total FROM transactions
                            WHERE account_id=%s AND type IN ('withdrawal','transfer_out')
                            AND DATE(created_at)=CURDATE() AND status='success'""", (account_id,))
            already_used = Decimal(cur.fetchone()["total"])
            if already_used + amount > Decimal(account["daily_limit"]):
                raise HTTPException(status_code=422, detail="Daily debit limit exceeded")
            if current < amount:
                raise HTTPException(status_code=422, detail="Insufficient balance")
            updated = current - amount
        else:
            updated = current + amount
            if updated > Decimal("9999999999.99"):
                raise HTTPException(status_code=422, detail="Account balance limit exceeded")
        cur.execute("UPDATE accounts SET balance=%s WHERE id=%s", (updated, account_id))
        reference = "ATM-" + uuid4().hex[:16].upper()
        cur.execute("""INSERT INTO transactions
            (transaction_reference,account_id,type,amount,status,description,balance_after,idempotency_key)
            VALUES(%s,%s,%s,%s,'success',%s,%s,%s)""",
            (reference, account_id, kind, amount, description, updated, key))
        transaction_id = cur.lastrowid
        cur.execute("INSERT INTO transaction_entries(transaction_id,account_id,entry_type,amount) VALUES(%s,%s,%s,%s)",
                    (transaction_id, account_id, "debit" if debit else "credit", amount))
        conn.commit()
        return {"message": "Simulated transaction successful", "reference": reference,
                "new_balance": money(updated), "simulation_only": True}
    except Error as exc:
        conn.rollback()
        if exc.errno == 1062:
            raise HTTPException(status_code=409, detail="Duplicate transaction request")
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


@router.post("/withdraw", status_code=201)
def withdraw(body: AmountRequest, user=Depends(customer_user), conn=Depends(get_db)):
    if body.amount % Decimal("100") != 0:
        raise HTTPException(status_code=422, detail="Withdrawal must be in multiples of ₹100")
    return _post_single_transaction(conn, user["account_id"], body.amount, "withdrawal",
                                    "Simulated withdrawal - no cash dispensed", body.idempotency_key, True)


@router.post("/deposit", status_code=201)
def deposit(body: AmountRequest, user=Depends(customer_user), conn=Depends(get_db)):
    return _post_single_transaction(conn, user["account_id"], body.amount, "deposit",
                                    "Simulated demo deposit", body.idempotency_key, False)


@router.get("/beneficiaries")
def beneficiaries(user=Depends(customer_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT a.account_number,c.full_name FROM accounts a
                    JOIN customers c ON c.id=a.customer_id
                    WHERE a.status='active' AND c.status='active' AND a.id<>%s ORDER BY c.full_name""",
                (user["account_id"],))
    rows = cur.fetchall()
    cur.close()
    return {"beneficiaries": rows}


@router.post("/transfer", status_code=201)
def transfer(body: TransferRequest, user=Depends(customer_user), conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""SELECT a.id,a.account_number,a.status,c.status AS customer_status
                        FROM accounts a JOIN customers c ON c.id=a.customer_id
                        WHERE a.account_number=%s""", (body.beneficiary_account_number,))
        beneficiary = cur.fetchone()
        if (not beneficiary or beneficiary["status"] != "active"
                or beneficiary["customer_status"] != "active"):
            raise HTTPException(status_code=404, detail="Eligible beneficiary not found")
        sender_id, receiver_id = user["account_id"], beneficiary["id"]
        if sender_id == receiver_id:
            raise HTTPException(status_code=422, detail="Cannot transfer to the same account")
        cur.execute("SELECT id FROM transactions WHERE idempotency_key=%s", (body.idempotency_key,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Duplicate transfer request")
        # Always lock account rows in ascending ID order to reduce deadlock risk.
        account_ids = sorted([sender_id, receiver_id])
        cur.execute("SELECT id,balance,status,daily_limit,transaction_limit FROM accounts WHERE id IN (%s,%s) ORDER BY id FOR UPDATE",
                    tuple(account_ids))
        locked = {row["id"]: row for row in cur.fetchall()}
        sender, receiver = locked[sender_id], locked[receiver_id]
        if sender["status"] != "active" or receiver["status"] != "active":
            raise HTTPException(status_code=403, detail="Both accounts must be active")
        if body.amount > Decimal(sender["transaction_limit"]):
            raise HTTPException(status_code=422, detail="Per-transaction limit exceeded")
        cur.execute("""SELECT COALESCE(SUM(amount),0) AS total FROM transactions
                        WHERE account_id=%s AND type IN ('withdrawal','transfer_out')
                        AND DATE(created_at)=CURDATE() AND status='success'""", (sender_id,))
        daily_used = Decimal(cur.fetchone()["total"])
        if daily_used + body.amount > Decimal(sender["daily_limit"]):
            raise HTTPException(status_code=422, detail="Daily debit limit exceeded")
        sender_balance, receiver_balance = Decimal(sender["balance"]), Decimal(receiver["balance"])
        if sender_balance < body.amount:
            raise HTTPException(status_code=422, detail="Insufficient balance")
        sender_after, receiver_after = sender_balance - body.amount, receiver_balance + body.amount
        if receiver_after > Decimal("9999999999.99"):
            raise HTTPException(status_code=422, detail="Beneficiary balance limit exceeded")
        cur.execute("UPDATE accounts SET balance=%s WHERE id=%s", (sender_after, sender_id))
        cur.execute("UPDATE accounts SET balance=%s WHERE id=%s", (receiver_after, receiver_id))
        reference = "TRF-" + uuid4().hex[:16].upper()
        cur.execute("INSERT INTO transfers(transfer_reference,sender_account_id,beneficiary_account_id,amount) VALUES(%s,%s,%s,%s)",
                    (reference, sender_id, receiver_id, body.amount))
        cur.execute("""INSERT INTO transactions(transaction_reference,account_id,type,amount,status,description,balance_after,idempotency_key)
                        VALUES(%s,%s,'transfer_out',%s,'success',%s,%s,%s)""",
                    (reference + "-OUT", sender_id, body.amount, "Demo transfer to " + beneficiary["account_number"], sender_after, body.idempotency_key))
        out_id = cur.lastrowid
        cur.execute("""INSERT INTO transactions(transaction_reference,account_id,type,amount,status,description,balance_after)
                        VALUES(%s,%s,'transfer_in',%s,'success','Demo transfer received',%s)""",
                    (reference + "-IN", receiver_id, body.amount, receiver_after))
        in_id = cur.lastrowid
        cur.execute("INSERT INTO transaction_entries(transaction_id,account_id,entry_type,amount) VALUES(%s,%s,'debit',%s)", (out_id, sender_id, body.amount))
        cur.execute("INSERT INTO transaction_entries(transaction_id,account_id,entry_type,amount) VALUES(%s,%s,'credit',%s)", (in_id, receiver_id, body.amount))
        conn.commit()
        return {"message": "Demo transfer successful", "reference": reference,
                "new_balance": money(sender_after), "beneficiary_account": "••••" + beneficiary["account_number"][-4:],
                "simulation_only": True}
    except Error as exc:
        conn.rollback()
        if exc.errno == 1062:
            raise HTTPException(status_code=409, detail="Duplicate transfer request")
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


@router.post("/change-pin")
def change_pin(body: ChangePinRequest, user=Depends(customer_user), conn=Depends(get_db)):
    if body.current_pin == body.new_pin:
        raise HTTPException(status_code=422, detail="New PIN must differ from current PIN")
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT pin_hash FROM demo_credentials WHERE account_id=%s FOR UPDATE", (user["account_id"],))
    row = cur.fetchone()
    if not row or not verify_secret(body.current_pin, row["pin_hash"]):
        conn.rollback()
        cur.close()
        raise HTTPException(status_code=401, detail="Current PIN is incorrect")
    cur.execute("UPDATE demo_credentials SET pin_hash=%s,failed_attempts=0,locked_until=NULL WHERE account_id=%s",
                (hash_secret(body.new_pin), user["account_id"]))
    conn.commit()
    cur.close()
    return {"message": "Demo PIN changed. Sign in again."}
