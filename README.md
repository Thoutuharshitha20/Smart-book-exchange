# Smart Book Exchange System

A student project built with Flask, SQLite, HTML, CSS, JavaScript, and Bootstrap.

## Features
- Student registration and login with password hashing
- Add and browse books for exchange or donation
- Upload optional JPG/PNG book cover photos shown in listings and book details
- Search and filter books by subject and semester
- Submit book requests and prevent requests for your own books
- Owner dashboard for accepting/rejecting requests and marking accepted requests completed
- Active request and completed transaction counters
- Incoming requests, outgoing requests, and history shown per logged-in student
- Completed transactions remain visible in both students' dashboards
- After a request is accepted, both students can see each other's account email in their dashboards to arrange a handoff themselves
- In-app guidance explains donations, exchanges, and safe in-person campus handoffs

## Requirements
- Python 3.10 or newer
- Visual Studio Code
- A web browser

## Run on Windows (PowerShell)
Open the extracted project folder in VS Code and run these commands in its terminal:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000 in your browser. The SQLite database (`books.db`) is created automatically on first run.

## Test the complete request workflow
1. Register Student A and log in.
2. Add a book with type Exchange or Donation.
3. Log out; register/log in as Student B.
4. Browse books, open Student A's book, and send a request.
5. Open Student B's dashboard and check **My Requests / History** for Pending.
6. Log in as Student A and open **Requests Received**. Accept the request.
7. Both students can now see each other's account email on their dashboards. They arrange a public campus handoff by email; for an exchange, they agree what to swap.
8. After the book is handed over, Student A selects **Mark completed**.
9. Verify both dashboards show the Completed status and updated counters.

There is no mediator or delivery service in the app. Donations are free, while exchange terms and the in-person handoff are arranged directly by the students.

The request actions validate ownership and status transitions. Accepting one request rejects other pending requests for that same book, and completed books are no longer available for new requests.

## Notes
- The updated code was syntax-checked. A full Flask test-client run could not be executed in the preparation environment because Flask could not be installed there. Please run the manual workflow above on your computer after installing requirements.
- Before public deployment, replace `app.secret_key`, add CSRF protection, and review production security settings.
