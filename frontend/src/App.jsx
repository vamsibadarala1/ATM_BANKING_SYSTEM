import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './style.css';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001/api/v1'
});

api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('atm_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const money = value =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR'
  }).format(Number(value || 0));

const makeKey = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;

const menuItems = [
  { id: 'balance', icon: '₹', label: 'BALANCE INQUIRY' },
  { id: 'withdraw', icon: '▣', label: 'CASH WITHDRAWAL' },
  { id: 'deposit', icon: '▤', label: 'CASH DEPOSIT' },
  { id: 'transfer', icon: '⇄', label: 'FUND TRANSFER' },
  { id: 'statement', icon: '▧', label: 'MINI STATEMENT' },
  { id: 'pin', icon: '●', label: 'CHANGE PIN' }
];

export default function App() {
  const [token, setToken] = useState(sessionStorage.getItem('atm_token'));
  const [mode, setMode] = useState(
    sessionStorage.getItem('atm_role') === 'admin' ? 'admin' : 'customer'
  );

  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState('overview');
  const [balance, setBalance] = useState(null);
  const [rows, setRows] = useState([]);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState(null);

  const run = async fn => {
    setBusy(true);
    setError('');
    setNotice('');

    try {
      await fn();
    } catch (err) {
      const detail = err.response?.data?.detail;

      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map(item => item.msg || 'Validation error').join(', '));
      } else {
        setError('Request failed. Please check the API and database.');
      }

      console.error('API Error:', err.response?.data || err.message);
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    const [balanceResponse, statementResponse] = await Promise.all([
      api.get('/atm/balance'),
      api.get('/atm/mini-statement')
    ]);

    setBalance(balanceResponse.data);
    setRows(statementResponse.data.transactions || []);
  };

  const loadAdmin = async () => {
    const response = await api.get('/admin/dashboard');
    setStats(response.data);
  };

  useEffect(() => {
    if (!token) return;

    if (mode === 'admin') {
      run(loadAdmin);
    } else {
      run(async () => {
        const response = await api.get('/atm/me');
        setProfile(response.data);
        await refresh();
      });
    }
    // Run once when restoring a saved session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async ({ identity, secret }) => {
    await run(async () => {
      const response = await api.post(
        mode === 'admin' ? '/admin/login' : '/atm/login',
        mode === 'admin'
          ? { email: identity, password: secret }
          : { account_number: identity, pin: secret }
      );

      const newToken = response.data.access_token;

      sessionStorage.setItem('atm_token', newToken);
      sessionStorage.setItem('atm_role', mode);

      setToken(newToken);
      setProfile(response.data.profile || null);

      if (mode === 'admin') {
        await loadAdmin();
        setTab('dashboard');
      } else {
        const profileResponse = await api.get('/atm/me');
        setProfile(profileResponse.data);
        await refresh();
        setTab('overview');
      }
    });
  };

  const logout = async () => {
    try {
      await api.post('/atm/logout');
    } catch (err) {
      console.warn('Logout API could not be reached:', err.message);
    }

    sessionStorage.removeItem('atm_token');
    sessionStorage.removeItem('atm_role');

    setToken(null);
    setProfile(null);
    setBalance(null);
    setRows([]);
    setBeneficiaries([]);
    setStats(null);
    setError('');
    setNotice('');
    setTab('overview');
    setMode('customer');
  };

  const txn = async (path, amount, extra = {}) => {
    await run(async () => {
      const response = await api.post(path, {
        amount: Number(amount),
        idempotency_key: makeKey(),
        ...extra
      });

      const data = response.data;

      setNotice(
        `${data.message || 'Transaction completed successfully.'} ${
          data.reference ? `Reference: ${data.reference}.` : ''
        } ${
          data.new_balance != null
            ? `Available balance: ${money(data.new_balance)}`
            : ''
        }`
      );

      await refresh();
      setTab('overview');
    });
  };

  if (!token) {
    return (
      <ATMLogin
        mode={mode}
        setMode={setMode}
        onLogin={login}
        busy={busy}
        error={error}
      />
    );
  }

  if (mode === 'admin') {
    return (
      <Admin
        api={api}
        run={run}
        stats={stats}
        logout={logout}
        error={error}
      />
    );
  }

  return (
    <ATMFrame
      profile={profile}
      tab={tab}
      setTab={setTab}
      busy={busy}
      logout={logout}
      error={error}
      notice={notice}
    >
      {tab === 'overview' && (
        <ATMHome
          balance={balance}
          profile={profile}
          setTab={setTab}
        />
      )}

      {tab === 'balance' && (
        <BalanceScreen balance={balance} onBack={() => setTab('overview')} />
      )}

      {tab === 'withdraw' && (
        <AmountScreen
          title="CASH WITHDRAWAL"
          subtitle="Select or enter the amount you want to withdraw."
          action="CONFIRM WITHDRAWAL"
          onBack={() => setTab('overview')}
          onSubmit={value => txn('/atm/withdraw', value)}
          multiplesOfHundred
        />
      )}

      {tab === 'deposit' && (
        <AmountScreen
          title="CASH DEPOSIT"
          subtitle="Simulated deposit. No physical cash is accepted."
          action="CONFIRM DEPOSIT"
          onBack={() => setTab('overview')}
          onSubmit={value => txn('/atm/deposit', value)}
        />
      )}

      {tab === 'transfer' && (
        <TransferScreen
          api={api}
          run={run}
          items={beneficiaries}
          setItems={setBeneficiaries}
          submit={(value, account) =>
            txn('/atm/transfer', value, {
              beneficiary_account_number: account
            })
          }
          onBack={() => setTab('overview')}
        />
      )}

      {tab === 'statement' && (
        <StatementScreen
          rows={rows}
          refresh={() => run(refresh)}
          onBack={() => setTab('overview')}
        />
      )}

      {tab === 'pin' && (
        <PinScreen
          api={api}
          run={run}
          done={logout}
          onBack={() => setTab('overview')}
        />
      )}
    </ATMFrame>
  );
}

/* -------------------------------------------------------
   ATM LOGIN SCREEN
------------------------------------------------------- */

function ATMLogin({ mode, setMode, onLogin, busy, error }) {
  const [cardInserted, setCardInserted] = useState(false);
  const [identity, setIdentity] = useState('');
  const [pin, setPin] = useState('');
  const [password, setPassword] = useState('');

  const addDigit = digit => {
    if (mode === 'customer') {
      if (pin.length < 8) setPin(old => old + digit);
    } else {
      setPassword(old => old + digit);
    }
  };

  const clearKeypad = () => {
    if (mode === 'customer') setPin('');
    else setPassword('');
  };

  const removeDigit = () => {
    if (mode === 'customer') setPin(old => old.slice(0, -1));
    else setPassword(old => old.slice(0, -1));
  };

  const submit = event => {
    event.preventDefault();

    onLogin({
      identity: identity.trim(),
      secret: mode === 'customer' ? pin : password
    });
  };

  return (
    <div className="atm-page">
      <div className="atm-machine login-machine">
        <div className="machine-top">
          <div className="machine-brand">
            <div className="brand-symbol">ATM</div>
            <div>
              <strong>SECURE BANKING</strong>
              <span>SELF SERVICE TERMINAL</span>
            </div>
          </div>
          <div className="machine-indicator">
            <span className="indicator-light" />
            SYSTEM ONLINE
          </div>
        </div>

        <div className="machine-bezel">
          <div className="screen">
            {!cardInserted ? (
              <div className="welcome-screen">
                <div className="screen-bank-logo">ATM</div>
                <p className="screen-overline">WELCOME TO</p>
                <h1>ATM BANKING</h1>
                <p className="screen-description">
                  Your self-service banking simulator
                </p>

                <div className="card-animation">
                  <div className="demo-card">
                    <div className="card-chip" />
                    <span>DEMO BANK</span>
                    <small>**** **** **** 1234</small>
                  </div>
                  <div className="card-slot">
                    <span />
                  </div>
                </div>

                <button
                  className="screen-button insert-button"
                  onClick={() => setCardInserted(true)}
                >
                  INSERT DEMO CARD
                  <span>→</span>
                </button>

                <p className="screen-footnote">
                  SIMULATION ONLY • NO REAL BANKING TRANSACTIONS
                </p>

                <button
                  className="admin-entry"
                  onClick={() => {
                    setMode('admin');
                    setCardInserted(true);
                  }}
                >
                  Administrator access
                </button>
              </div>
            ) : (
              <form className="pin-screen" onSubmit={submit}>
                <div className="screen-heading">
                  <span className="screen-overline">SECURE ACCESS</span>
                  <h2>{mode === 'admin' ? 'ADMIN LOGIN' : 'CUSTOMER VERIFICATION'}</h2>
                  <p>
                    {mode === 'admin'
                      ? 'Enter administrator credentials.'
                      : 'Enter your demo account number and PIN.'}
                  </p>
                </div>

                {mode === 'customer' ? (
                  <>
                    <label>ACCOUNT NUMBER</label>
                    <input
                      value={identity}
                      onChange={event => setIdentity(event.target.value)}
                      placeholder="Enter account number"
                      inputMode="numeric"
                      required
                    />

                    <label>ENTER YOUR PIN</label>
                    <div className="pin-display">
                      {Array.from({ length: 4 }).map((_, index) => (
                        <span key={index}>
                          {pin[index] ? '●' : '○'}
                        </span>
                      ))}
                      {pin.length > 4 && (
                        <small>+{pin.length - 4}</small>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <label>ADMIN EMAIL</label>
                    <input
                      type="email"
                      value={identity}
                      onChange={event => setIdentity(event.target.value)}
                      placeholder="Administrator email"
                      required
                    />
                    <label>ADMIN PASSWORD</label>
                    <input
                      type="password"
                      value={password}
                      onChange={event => setPassword(event.target.value)}
                      placeholder="Enter password"
                      required
                    />
                  </>
                )}

                {mode === 'customer' && (
                  <div className="atm-keypad">
                    {['1', '2', '3', '4', '5', '6', '7', '8', '9', 'CLEAR', '0', '⌫'].map(key => (
                      <button
                        type="button"
                        key={key}
                        className={key === 'CLEAR' ? 'key-clear' : ''}
                        onClick={() => {
                          if (key === 'CLEAR') clearKeypad();
                          else if (key === '⌫') removeDigit();
                          else addDigit(key);
                        }}
                      >
                        {key}
                      </button>
                    ))}
                  </div>
                )}

                {error && <div className="screen-error">{error}</div>}

                <div className="screen-actions">
                  <button
                    type="button"
                    className="screen-button secondary-screen-button"
                    onClick={() => {
                      setCardInserted(false);
                      setPin('');
                      setPassword('');
                      setIdentity('');
                      setMode('customer');
                    }}
                  >
                    CANCEL
                  </button>
                  <button
                    type="submit"
                    className="screen-button"
                    disabled={
                      busy ||
                      !identity.trim() ||
                      (mode === 'customer' ? pin.length < 4 : !password)
                    }
                  >
                    {busy ? 'VERIFYING...' : 'ENTER'}
                  </button>
                </div>

                <p className="screen-footnote">
                  {mode === 'customer'
                    ? 'DEMO CUSTOMER: 1000001234 / 1234'
                    : 'AUTHORIZED ADMINISTRATORS ONLY'}
                </p>
              </form>
            )}
          </div>
        </div>

        <ATMHardware />
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   PHYSICAL ATM FRAME
------------------------------------------------------- */

function ATMHardware() {
  return (
    <div className="hardware">
      <div className="hardware-side">
        <div className="speaker-grille">
          {Array.from({ length: 8 }).map((_, i) => <span key={i} />)}
        </div>
        <div className="hardware-label">SCREEN CONTROL</div>
        <div className="side-buttons">
          {[1, 2, 3, 4].map(n => <span key={n} />)}
        </div>
      </div>

      <div className="hardware-center">
        <div className="hardware-section">
          <span className="hardware-led" />
          <b>CARD READER</b>
          <div className="card-reader-slot"><span /></div>
        </div>

        <div className="hardware-section">
          <b>RECEIPT</b>
          <div className="receipt-slot" />
        </div>

        <div className="hardware-section cash-section">
          <b>CASH DISPENSER</b>
          <div className="cash-slot"><span /></div>
        </div>
      </div>

      <div className="hardware-side right-hardware">
        <div className="speaker-grille">
          {Array.from({ length: 8 }).map((_, i) => <span key={i} />)}
        </div>
        <div className="hardware-label">PIN PAD</div>
        <div className="physical-keypad">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', 'E'].map(key => (
            <span key={key}>{key}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   CUSTOMER ATM SCREEN
------------------------------------------------------- */

function ATMFrame({
  profile,
  tab,
  setTab,
  busy,
  logout,
  error,
  notice,
  children
}) {
  const currentTitle =
    menuItems.find(item => item.id === tab)?.label || 'ATM MAIN MENU';

  return (
    <div className="atm-page">
      <div className="atm-machine">
        <div className="machine-top">
          <div className="machine-brand">
            <div className="brand-symbol">ATM</div>
            <div>
              <strong>SECURE BANKING</strong>
              <span>SELF SERVICE TERMINAL</span>
            </div>
          </div>
          <div className="machine-indicator">
            <span className="indicator-light" />
            {busy ? 'PROCESSING' : 'SYSTEM ONLINE'}
          </div>
        </div>

        <div className="machine-bezel">
          <div className="screen customer-screen">
            <div className="screen-status">
              <span>ATM BANKING SIMULATOR</span>
              <span>● SECURE SESSION</span>
            </div>

            <div className="screen-userbar">
              <div>
                <small>WELCOME</small>
                <strong>{profile?.full_name || profile?.name || 'CUSTOMER'}</strong>
              </div>
              <button onClick={logout}>EXIT / EJECT CARD</button>
            </div>

            <div className="screen-page-title">
              <span>{currentTitle}</span>
              <span className="screen-time-label">DEMO TERMINAL</span>
            </div>

            {error && <div className="screen-alert error-alert">{error}</div>}
            {notice && <div className="screen-alert success-alert">{notice}</div>}

            {children}

            <div className="screen-bottom">
              <span>PLEASE TAKE YOUR CARD</span>
              <span>THANK YOU FOR BANKING WITH US</span>
            </div>
          </div>
        </div>

        <ATMHardware />
      </div>
    </div>
  );
}

function ATMHome({ balance, profile, setTab }) {
  return (
    <div className="home-screen">
      <div className="welcome-banner">
        <div>
          <small>AVAILABLE BALANCE</small>
          <h2>{money(balance?.balance)}</h2>
          <span>Account ending in {balance?.account_number?.slice(-4) || '----'}</span>
        </div>
        <div className="balance-symbol">₹</div>
      </div>

      <div className="menu-instruction">
        PLEASE SELECT YOUR TRANSACTION
      </div>

      <div className="atm-menu-grid">
        {menuItems.map(item => (
          <button
            className="atm-menu-button"
            key={item.id}
            onClick={() => setTab(item.id)}
          >
            <span className="menu-icon">{item.icon}</span>
            <span>{item.label}</span>
            <b>›</b>
          </button>
        ))}
      </div>

      <div className="screen-tip">
        <span>ℹ</span>
        Select an option to continue. All transactions use fictional demo funds.
      </div>
    </div>
  );
}

function BalanceScreen({ balance, onBack }) {
  return (
    <div className="transaction-screen">
      <div className="transaction-result">
        <div className="result-icon">₹</div>
        <small>YOUR AVAILABLE BALANCE</small>
        <h2>{money(balance?.balance)}</h2>
        <p>Account number: {balance?.account_number || 'Not available'}</p>
        <span className="result-status">BALANCE INQUIRY SUCCESSFUL</span>
      </div>
      <ScreenControls onBack={onBack} />
    </div>
  );
}

function AmountScreen({
  title,
  subtitle,
  action,
  onBack,
  onSubmit,
  multiplesOfHundred = false
}) {
  const [amount, setAmount] = useState('');

  const presets = multiplesOfHundred
    ? ['500', '1000', '2000', '5000']
    : ['500', '1000', '2000', '5000'];

  const validAmount =
    Number(amount) > 0 &&
    Number.isFinite(Number(amount)) &&
    (!multiplesOfHundred || Number(amount) % 100 === 0);

  return (
    <div className="transaction-screen">
      <div className="transaction-instructions">
        <span className="instruction-icon">₹</span>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>

      <label className="atm-label">ENTER AMOUNT (INR)</label>
      <div className="amount-display">
        <span>₹</span>
        <input
          type="number"
          min="100"
          step={multiplesOfHundred ? '100' : '0.01'}
          value={amount}
          onChange={event => setAmount(event.target.value)}
          placeholder="0.00"
        />
      </div>

      <div className="preset-label">QUICK AMOUNT SELECTION</div>
      <div className="preset-grid">
        {presets.map(value => (
          <button key={value} onClick={() => setAmount(value)}>
            ₹{Number(value).toLocaleString('en-IN')}
          </button>
        ))}
      </div>

      {multiplesOfHundred && amount && !validAmount && (
        <p className="validation-message">
          Withdrawal amount must be a multiple of ₹100.
        </p>
      )}

      <div className="screen-actions">
        <button className="screen-button secondary-screen-button" onClick={onBack}>
          CANCEL
        </button>
        <button
          className="screen-button"
          disabled={!validAmount}
          onClick={() => {
            if (window.confirm(`Confirm ${title.toLowerCase()} of ${money(amount)}?`)) {
              onSubmit(amount);
            }
          }}
        >
          {action}
        </button>
      </div>
    </div>
  );
}

function TransferScreen({ api, run, items, setItems, submit, onBack }) {
  const [account, setAccount] = useState('');
  const [amount, setAmount] = useState('');

  useEffect(() => {
    run(async () => {
      const response = await api.get('/atm/beneficiaries');
      setItems(response.data.beneficiaries || []);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="transaction-screen">
      <div className="transaction-instructions">
        <span className="instruction-icon">⇄</span>
        <h2>FUND TRANSFER</h2>
        <p>Transfer demo funds to another registered simulator account.</p>
      </div>

      <label className="atm-label">SELECT BENEFICIARY</label>
      <select
        className="atm-select"
        value={account}
        onChange={event => setAccount(event.target.value)}
      >
        <option value="">Choose beneficiary account</option>
        {items.map(item => (
          <option key={item.account_number} value={item.account_number}>
            {item.full_name} — {item.account_number}
          </option>
        ))}
      </select>

      <label className="atm-label">TRANSFER AMOUNT</label>
      <div className="amount-display">
        <span>₹</span>
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={amount}
          onChange={event => setAmount(event.target.value)}
          placeholder="0.00"
        />
      </div>

      <div className="screen-actions">
        <button className="screen-button secondary-screen-button" onClick={onBack}>
          CANCEL
        </button>
        <button
          className="screen-button"
          disabled={!account || Number(amount) <= 0}
          onClick={() => {
            if (window.confirm(`Confirm transfer of ${money(amount)}?`)) {
              submit(amount, account);
            }
          }}
        >
          CONFIRM TRANSFER
        </button>
      </div>
    </div>
  );
}

function StatementScreen({ rows, refresh, onBack }) {
  return (
    <div className="transaction-screen statement-screen">
      <div className="statement-heading">
        <div>
          <h2>MINI STATEMENT</h2>
          <p>YOUR RECENT DEMO TRANSACTIONS</p>
        </div>
        <button className="small-screen-button" onClick={refresh}>
          REFRESH
        </button>
      </div>

      {!rows?.length ? (
        <div className="empty-statement">
          <span>▤</span>
          <h3>NO TRANSACTIONS FOUND</h3>
          <p>Your transaction history will appear here.</p>
        </div>
      ) : (
        <div className="atm-table-wrap">
          <table className="atm-table">
            <thead>
              <tr>
                <th>TYPE</th>
                <th>AMOUNT</th>
                <th>DATE</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, index) => (
                <tr key={item.transaction_reference || index}>
                  <td>{item.type}</td>
                  <td>{money(item.amount)}</td>
                  <td>
                    {item.created_at
                      ? new Date(item.created_at).toLocaleDateString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ScreenControls onBack={onBack} />
    </div>
  );
}

function PinScreen({ api, run, done, onBack }) {
  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');

  const changePin = async () => {
    await run(async () => {
      await api.post('/atm/change-pin', {
        current_pin: currentPin,
        new_pin: newPin
      });

      alert('PIN changed successfully. Please sign in again.');
      done();
    });
  };

  return (
    <div className="transaction-screen">
      <div className="transaction-instructions">
        <span className="instruction-icon">●</span>
        <h2>CHANGE YOUR PIN</h2>
        <p>Enter your current PIN and choose a new 4–8 digit PIN.</p>
      </div>

      <label className="atm-label">CURRENT PIN</label>
      <input
        className="atm-input"
        type="password"
        inputMode="numeric"
        maxLength="8"
        value={currentPin}
        onChange={event => setCurrentPin(event.target.value.replace(/\D/g, ''))}
      />

      <label className="atm-label">NEW PIN</label>
      <input
        className="atm-input"
        type="password"
        inputMode="numeric"
        maxLength="8"
        value={newPin}
        onChange={event => setNewPin(event.target.value.replace(/\D/g, ''))}
      />

      <div className="screen-actions">
        <button className="screen-button secondary-screen-button" onClick={onBack}>
          CANCEL
        </button>
        <button
          className="screen-button"
          disabled={
            !/^\d{4,8}$/.test(currentPin) ||
            !/^\d{4,8}$/.test(newPin) ||
            currentPin === newPin
          }
          onClick={changePin}
        >
          UPDATE PIN
        </button>
      </div>
    </div>
  );
}

function ScreenControls({ onBack }) {
  return (
    <div className="screen-actions">
      <button className="screen-button secondary-screen-button" onClick={onBack}>
        BACK TO MAIN MENU
      </button>
    </div>
  );
}

/* -------------------------------------------------------
   ADMIN CONSOLE – SEPARATE FROM CUSTOMER ATM
------------------------------------------------------- */

function Admin({ api, run, stats, logout, error }) {
  const [tab, setTab] = useState('dashboard');
  const [customers, setCustomers] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [transactions, setTransactions] = useState([]);

  const load = async () => {
    await run(async () => {
      if (tab === 'customers') {
        const response = await api.get('/admin/customers');
        setCustomers(response.data.customers || []);
      }

      if (tab === 'accounts') {
        const response = await api.get('/admin/accounts');
        setAccounts(response.data.accounts || []);
      }

      if (tab === 'transactions') {
        const response = await api.get('/admin/transactions');
        setTransactions(response.data.transactions || []);
      }
    });
  };

  useEffect(() => {
    if (tab !== 'dashboard') load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const createCustomer = event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);

    run(async () => {
      await api.post('/admin/customers', {
        full_name: data.get('name'),
        email: data.get('email'),
        phone: data.get('phone'),
        account_number: data.get('account'),
        initial_balance: Number(data.get('balance')),
        pin: data.get('pin'),
        daily_limit: 20000,
        transaction_limit: 10000
      });

      alert('Demo customer created successfully.');
      form.reset();

      const response = await api.get('/admin/customers');
      setCustomers(response.data.customers || []);
    });
  };

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div className="admin-brand">
          <div className="admin-logo">ATM</div>
          <div>
            <strong>ATM ADMINISTRATION</strong>
            <small>Banking simulator control panel</small>
          </div>
        </div>
        <button className="admin-exit" onClick={logout}>SIGN OUT</button>
      </header>

      <main className="admin-content">
        <div className="admin-title">
          <div>
            <span>CONTROL CENTER</span>
            <h1>Administration</h1>
          </div>
          <span className="admin-badge">DEMO ENVIRONMENT</span>
        </div>

        {error && <div className="admin-error">{error}</div>}

        <div className="admin-tabs">
          {[
            ['dashboard', 'Dashboard'],
            ['customers', 'Customers'],
            ['accounts', 'Accounts'],
            ['transactions', 'Transactions']
          ].map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? 'selected' : ''}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'dashboard' && (
          <div className="admin-stats">
            {[
              ['Customers', stats?.customers],
              ['Accounts', stats?.accounts],
              ['Active accounts', stats?.active_accounts],
              ['Transactions', stats?.transactions],
              ['Simulated volume', money(stats?.simulated_volume)]
            ].map(([label, value]) => (
              <div className="admin-stat" key={label}>
                <span>{label}</span>
                <strong>{value ?? '—'}</strong>
              </div>
            ))}
          </div>
        )}

        {tab === 'customers' && (
          <>
            <section className="admin-panel">
              <h2>Create fictional customer</h2>
              <form className="admin-create-form" onSubmit={createCustomer}>
                <input name="name" placeholder="Full name" required minLength="2" />
                <input name="email" type="email" placeholder="Email" required />
                <input name="phone" placeholder="Demo phone" />
                <input
                  name="account"
                  placeholder="Unique account number"
                  required
                  minLength="6"
                  pattern="[0-9]+"
                />
                <input
                  name="balance"
                  type="number"
                  placeholder="Initial balance"
                  min="0"
                  step="0.01"
                  required
                />
                <input
                  name="pin"
                  placeholder="Demo PIN (4–8 digits)"
                  pattern="[0-9]{4,8}"
                  required
                />
                <button className="admin-primary">CREATE CUSTOMER</button>
              </form>
            </section>
            <AdminTable rows={customers} cols={['id', 'full_name', 'email', 'status', 'account_count']} />
          </>
        )}

        {tab === 'accounts' && (
          <AdminTable
            rows={accounts}
            cols={['account_number', 'full_name', 'balance', 'status', 'daily_limit', 'transaction_limit']}
          />
        )}

        {tab === 'transactions' && (
          <AdminTable
            rows={transactions}
            cols={['transaction_reference', 'account_number', 'full_name', 'type', 'amount', 'balance_after', 'created_at']}
          />
        )}
      </main>
    </div>
  );
}

function AdminTable({ rows = [], cols }) {
  return (
    <section className="admin-panel admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            {cols.map(column => (
              <th key={column}>{column.replaceAll('_', ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id || row.transaction_reference || index}>
              {cols.map(column => (
                <td key={column}>{String(row[column] ?? '—')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="admin-empty">No records available.</p>}
    </section>
  );
}
