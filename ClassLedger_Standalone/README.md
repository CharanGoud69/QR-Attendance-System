# ClassLedger — standalone QR attendance

A complete coaching-institute attendance website with its own admin and student ID/password login. No ChatGPT account, Google account, email invitation, or location permission is required.

## Start on Windows

1. Install **Python 3.12 or later** from python.org. Enable **Add Python to PATH** during installation.
2. Extract the entire ZIP. Do not run it from inside the ZIP preview.
3. Double-click **START_WINDOWS.bat**. The first run needs internet to install dependencies.
4. Create sir's admin ID and password when asked. Password input is hidden while typing; that is normal. There are no default passwords.
5. The app opens at **http://localhost:8000**. Sign in using the admin account you just created.
6. Keep the terminal window open. Closing it stops the website on this computer.

On later runs, use the same launcher. Your database and accounts remain in `data/`.

## Test with students on the same Wi-Fi

The host laptop and student phones must be on the same reachable network. Internet access by itself is not enough.

1. On the host laptop, open Command Prompt and run `ipconfig`.
2. Find the **IPv4 Address** under the active Wi-Fi adapter (for example, `192.168.1.5`). Use your real address, not this example.
3. Sign in as admin, open **Settings & backup**, and set the QR website address to `http://192.168.1.5:8000` using the actual address.
4. On a phone, open that address in the browser before generating a QR. It must load the ClassLedger login page.
5. If Windows asks, allow Python on your **private** network. Guest Wi-Fi or client isolation may block devices from reaching each other.
6. If the laptop's IP changes, update Settings and download fresh QR images.

A QR containing `localhost` will point to the student's own phone, not the host laptop. The QR screen warns you about this.

For access from different networks, deploy to independent online hosting with HTTPS. The laptop's local address is not a public link. For real use with student passwords, use HTTPS hosting; local HTTP is intended for a trusted-network test.

## Sir's daily workflow

1. Open **Students**. Add the student's name, unique ID, batch, and a temporary password (at least 8 characters).
2. Share the ID and temporary password privately with that student. The app does not send messages automatically.
3. Have students sign in and change their temporary passwords **before class**, so the first-use process does not consume the QR window.
4. Open **QR attendance**, choose the batch and **IN**, then generate the QR when the representative is ready.
5. Download the image and send it to the representative, or use Share if supported by your browser. The representative displays it for classmates.
6. Students scan with their phone camera, sign in if necessary, and tap **Confirm check-in**.
7. At class end, generate a separate **OUT** QR and repeat the process.
8. Refresh the register to see scans. Export a day's CSV or a month's detailed CSV when needed.

Each QR lasts **10 minutes from generation**, using server time. Generating another QR of the same type, batch, and date cancels the previous one. Cancellation is immediate. Downloading/sharing does not restart the timer.

## Attendance rules

- One IN and one OUT per student per calendar day, in **India time (IST)**.
- OUT requires an existing IN for that day.
- Repeated scans keep the original timestamp.
- Both scans: **Complete**.
- IN only: **Missing checkout**.
- Neither scan: **Not marked** until the batch's OUT window expires; then **Absent**.
- Cancelled OUT windows do not mark absences.
- No location check is performed. A forwarded QR can be used by another registered student of that batch while it remains active.
- Students see only their own scan history. Teacher pages, QR generation, exports and backups require an admin account.
- Accounts can stay signed in for 14 days. On a shared device, uncheck the remember option and sign out after use.

## Forgotten passwords / account management

- Sir can reset a student password in **Students**. This logs out existing sessions and forces the student to choose a new password at the next login.
- Archive students instead of deleting them. Their attendance history stays in reports.
- To add another teacher/admin on the host, run `python setup_admin.py` with the project virtual environment activated.
- To reset an existing admin password, run `python setup_admin.py --reset` from the host terminal. There is deliberately no public admin-account creation page.
- Passwords are stored as salted hashes, not plaintext.

## Share the project with a friend

Send the complete ZIP. Your friend extracts it and follows the Windows setup steps.

A fresh ZIP starts with a new, empty database. Separate installations do **not** automatically share records. To share one database, everyone must use the same running host (local Wi-Fi or online hosting).

To move an existing installation, stop the server and copy the full project **including its `data/` folder** privately to the new host. Update the QR website address. Do not send live account data in a public ZIP.

The earlier ChatGPT-hosted prototype is separate. Its records and accounts have not been imported into this version, and its old URL still uses ChatGPT login.

## Backups

**Settings & backup → Download database backup** creates a consistent SQLite backup containing accounts and attendance. Store it privately.

To restore: stop the app, preserve the existing `data/attendance.db` as a rollback copy, and replace it with the backup renamed `attendance.db`. Keep `data/secret.key` or the configured `SECRET_KEY` stable. Restart the app. A new signing key logs out everyone without deleting attendance.

## macOS / Linux

Install Python 3.12+, then run:

```bash
sh start_mac_linux.sh
```

If the OS needs a separate Python venv package, install it first. The launcher creates `.venv`, installs dependencies, performs local admin setup, and runs Waitress.

## Manual startup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python setup_admin.py --ensure
python app.py
```

## Independent hosting

This package includes a Dockerfile and a production Waitress server. A hosting account/connection is still required to publish an internet-accessible URL. Nothing in this ZIP creates or pays for a hosting account.

Configure the host with:

| Setting | Value |
| --- | --- |
| Runtime | Python 3.12+ or included Dockerfile |
| Install command | `pip install -r requirements.txt` |
| Start command | `python app.py` |
| Persistent storage | A writable directory such as `/data` |
| `DATA_DIR` | Path to that persistent directory |
| `PORT` | Host-assigned port, or `8000` |
| `PUBLIC_BASE_URL` | Actual public HTTPS origin, without a trailing path |
| `COOKIE_SECURE` | `1` on HTTPS hosting; `0` for local HTTP testing |
| `SECRET_KEY` | Optional strong random secret; otherwise generated and retained in `DATA_DIR/secret.key` |

Run `python setup_admin.py --ensure` in a private hosting shell to create the first admin. Do not put a password in source code or shell arguments.

Persist the database and signing key across restarts/deployments. An ephemeral filesystem will lose records. This SQLite version is intended for a single running app instance with local persistent storage; do not deploy multiple independent replicas with separate disks. If scaling to multiple instances, migrate to a shared database first.

The app listens on `0.0.0.0` and offers `/health` for host health checks. Use the hosting provider's HTTPS endpoint. A Dockerfile is supplied, but no cloud deployment has been performed by this package.

## Verification

Run the included tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover admin pages, PNG QR generation, local authentication, IN/OUT, exact-boundary expiry, cancellation/replacement, duplicates, wrong batches, OUT-before-IN, student isolation, CSRF, redirect validation, password resets, archiving, rate limiting, CSV output and backups.

Real-phone camera scanning and Windows launcher execution must still be checked on your devices. The app's HTTP routes and database behavior were tested in Linux.
