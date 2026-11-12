-- ATM simulator schema. All monetary amounts are fictional demo values.
CREATE DATABASE IF NOT EXISTS atm_practice CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE atm_practice;

CREATE TABLE IF NOT EXISTS customers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  phone VARCHAR(20) NOT NULL DEFAULT '',
  status ENUM('active','inactive') NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS accounts (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  account_number VARCHAR(20) NOT NULL UNIQUE,
  customer_id BIGINT UNSIGNED NOT NULL,
  balance DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  status ENUM('active','inactive','blocked','closed') NOT NULL DEFAULT 'active',
  daily_limit DECIMAL(12,2) NOT NULL DEFAULT 20000.00,
  transaction_limit DECIMAL(12,2) NOT NULL DEFAULT 10000.00,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_accounts_customer FOREIGN KEY(customer_id) REFERENCES customers(id),
  INDEX idx_account_status(status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS demo_credentials (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  account_id BIGINT UNSIGNED NOT NULL UNIQUE,
  pin_hash VARCHAR(255) NOT NULL,
  failed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_credentials_account FOREIGN KEY(account_id) REFERENCES accounts(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transactions (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  transaction_reference VARCHAR(40) NOT NULL UNIQUE,
  account_id BIGINT UNSIGNED NOT NULL,
  type ENUM('deposit','withdrawal','transfer_in','transfer_out','adjustment') NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  status ENUM('success','failed') NOT NULL DEFAULT 'success',
  description VARCHAR(255) NOT NULL DEFAULT '',
  balance_after DECIMAL(12,2) NOT NULL,
  idempotency_key VARCHAR(100) NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_transactions_account FOREIGN KEY(account_id) REFERENCES accounts(id),
  INDEX idx_txn_account_date(account_id,created_at),
  INDEX idx_txn_type_date(type,created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transfers (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  transfer_reference VARCHAR(40) NOT NULL UNIQUE,
  sender_account_id BIGINT UNSIGNED NOT NULL,
  beneficiary_account_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  status ENUM('success','failed') NOT NULL DEFAULT 'success',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_transfer_sender FOREIGN KEY(sender_account_id) REFERENCES accounts(id),
  CONSTRAINT fk_transfer_beneficiary FOREIGN KEY(beneficiary_account_id) REFERENCES accounts(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS transaction_entries (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  transaction_id BIGINT UNSIGNED NOT NULL,
  account_id BIGINT UNSIGNED NOT NULL,
  entry_type ENUM('debit','credit') NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_entry_transaction FOREIGN KEY(transaction_id) REFERENCES transactions(id),
  CONSTRAINT fk_entry_account FOREIGN KEY(account_id) REFERENCES accounts(id),
  INDEX idx_entries_account(account_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admin_users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','auditor') NOT NULL DEFAULT 'admin',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admin_audit (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  admin_user_id BIGINT UNSIGNED NOT NULL,
  action VARCHAR(100) NOT NULL,
  target_type VARCHAR(50) NOT NULL,
  target_id VARCHAR(50),
  reason VARCHAR(255) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_audit_admin FOREIGN KEY(admin_user_id) REFERENCES admin_users(id),
  INDEX idx_audit_created(created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS revoked_tokens (
  jti VARCHAR(100) PRIMARY KEY,
  expires_at DATETIME NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_revoked_expiry(expires_at)
) ENGINE=InnoDB;
