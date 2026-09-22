# 🟡 EliteMinus — locally hosted music + staff management

EliteMinus is a music listener application with a Flask staff-management
backend. It uses Python/MySQL on PythonAnywhere for the API and admin panel,
and a static Vanilla JavaScript client on Vercel for listeners.

![stack](https://img.shields.io/badge/Flask-3.x-black) ![db](https://img.shields.io/badge/MySQL-XAMPP-orange) ![css](https://img.shields.io/badge/Tailwind-CDN-38bdf8)

---

## ✨ Features

| Area | What you get |
|------|--------------|
| **Accounts** | Sign up with username, e-mail, password confirmation, and SMTP OTP verification. Passwords are bcrypt hashed. |
| **Home** | Greeting, recently played, trending, featured playlists, popular albums & artists. |
| **Search** | Live search across songs, artists, albums and playlists, plus a "Browse all" genre grid. |
| **Player** | Play/pause, next/previous, seek bar, volume + mute, **shuffle**, **repeat (off/all/one)**, spacebar shortcut. Playback survives navigation and page reloads. |
| **Playlists** | Create, edit, delete, add/remove songs, public/private. Your playlists show in the sidebar. |
| **Liked Songs** | Like/unlike anywhere; a dedicated Liked Songs collection. |
| **Albums** | Album pages with full track lists. |
| **Artists** | Artist pages with top songs, albums, bio, and **follow/unfollow**. |
| **Library** | All your playlists, followed artists and liked songs in one place. |
| **Queue** | A persistent, server-backed queue with add-next, remove, clear, and reorder. |
| **History** | Plays are recorded and power "Recently played". |
| **Cover art** | Generated on the fly by Flask as gradient SVGs — no image files needed, works offline. |
| **Staff management** | `/admin` provides staff roles, departments, status/approval, invites, password resets, auditing, CSV export, and catalog controls. |
| **Local MP3 library** | Admins upload MP3 files they own or are licensed to distribute; the app stores metadata in MySQL and streams files from PythonAnywhere. |
| **Music suggestions** | Listeners can submit a title and YouTube reference link for administrator review. |

> Audio uses royalty-free demo tracks from soundhelix.com, so playback needs an
> internet connection. Everything else works locally.

---

## Project layout

```text
EliteMinus/
├── backend/                 # Deploy this folder to PythonAnywhere
│   ├── app.py               # Flask API and server-rendered staff admin
│   ├── wsgi.py              # PythonAnywhere entry point
│   ├── models.py            # MySQL models (users, OTPs, queue, playlists, …)
│   ├── services/            # SMTP, OTP, token, and audit helpers
│   ├── blueprints/          # Auth, listener API, and admin routes
│   ├── templates/           # Admin + fallback auth pages
│   ├── static/              # Admin assets
│   ├── requirements.txt
│   ├── .env.example
│   ├── seed.py              # Fresh database setup
│   └── migrate.py           # Existing database upgrade
├── frontend/                # Deploy this folder to Vercel
│   ├── index.html           # Listener application
│   ├── login.html / register.html / verify.html / forgot.html
│   ├── js/config.js         # Set PythonAnywhere API URL here
│   └── vercel.json
└── DEPLOYMENT.md            # Complete PythonAnywhere + Vercel setup guide
```

## 🚀 Local quick start

### 1. Start MySQL
Open the **XAMPP Control Panel** and click **Start** next to **MySQL**.
(Apache is *not* required — Flask serves the site itself.)

### 2. Install the Python packages
From `backend/`:

```bash
cd backend
pip install -r requirements.txt
```

### 3. (Optional) configure the database connection
Defaults match a stock XAMPP install (`root`, no password, `127.0.0.1:3306`).
To change anything, copy `backend/.env.example` to `backend/.env` and edit it.

### 4. Create the database and sample data
This one command creates the `spotify_clone` database, all tables, and fills it
with artists, albums, 66 songs, curated playlists and a demo account:

```bash
python seed.py
```

### 5. Run the app
```bash
python app.py
```

The backend admin panel is at **http://localhost:5000/admin**. For the listener
UI, set `frontend/js/config.js` to `http://localhost:5000` and serve
`frontend/` with a static server.

Fresh sample data includes these development accounts:

| Account | Username | Password | OTP required |
| --- | --- | --- | --- |
| Administrator | `admin` | `Admin@12345` | No |
| Default test listener | `user` | `User@12345` | No — already verified |
| Demo listener | `demo` | `Demo@12345` | No — already verified |

Change or remove these accounts before production deployment.

If you already seeded the database before this account was added, create it
without deleting anything:

```bash
cd backend
python create_default_user.py
```

```
username:  demo
password:  demo12345
```

…or click **Sign up** to make your own account.

---

## Deploy

See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact folders, commands and settings
for PythonAnywhere, PythonAnywhere MySQL, Vercel, SMTP OTP, CORS, and MP3 uploads.

---

## 🛠️ Tech notes

- **Database:** MySQL/MariaDB via SQLAlchemy with the PyMySQL driver.
- **Auth:** Flask-Login admin sessions plus signed Bearer tokens for Vercel;
  passwords are hashed with Flask-Bcrypt and registration requires an e-mail OTP.
- **Frontend:** Tailwind via the Play CDN (no build step). For production you'd
  compile Tailwind with the CLI/PostCSS instead.
- **API:** all dynamic data is served as JSON under `/api/*`; frontend and
  backend can be deployed separately.

## ⚠️ Troubleshooting

- **`ERROR 1130: Host 'localhost' is not allowed` / can't connect:** your MariaDB
  privilege tables are corrupted. Stop MySQL, then from `C:\xampp\mysql\bin` run
  `aria_chk -o -f mysql\*.MAI` (run from `C:\xampp\mysql\data`), and start MySQL
  again.
- **`Access denied for user 'root'`:** set your real MySQL password in `.env`
  (`DB_PASSWORD=`).
- **Port 5000 in use:** another program (or a previous run) is using it. Stop it,
  or change the port at the bottom of `app.py`.
- **No sound:** demo audio streams from the internet — check your connection.
