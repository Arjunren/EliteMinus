# 🟡 EliteMinus- — a Spotify-style web app

A full-featured music-streaming web app built with **Python (Flask)**, **vanilla
JavaScript**, **HTML**, **Tailwind CSS**, and a **MySQL** database running on
**XAMPP**.

It's a single-page app: the player bar lives in one persistent shell, so music
keeps playing while you move between pages — just like Spotify.

![stack](https://img.shields.io/badge/Flask-3.x-black) ![db](https://img.shields.io/badge/MySQL-XAMPP-orange) ![css](https://img.shields.io/badge/Tailwind-CDN-38bdf8)

---

## ✨ Features

| Area | What you get |
|------|--------------|
| **Accounts** | Register, log in, log out. Passwords hashed with bcrypt, sessions via Flask-Login. |
| **Home** | Greeting, recently played, trending, featured playlists, popular albums & artists. |
| **Search** | Live search across songs, artists, albums and playlists, plus a "Browse all" genre grid. |
| **Player** | Play/pause, next/previous, seek bar, volume + mute, **shuffle**, **repeat (off/all/one)**, spacebar shortcut. Playback survives navigation and page reloads. |
| **Playlists** | Create, edit, delete, add/remove songs, public/private. Your playlists show in the sidebar. |
| **Liked Songs** | Like/unlike anywhere; a dedicated Liked Songs collection. |
| **Albums** | Album pages with full track lists. |
| **Artists** | Artist pages with top songs, albums, bio, and **follow/unfollow**. |
| **Library** | All your playlists, followed artists and liked songs in one place. |
| **Queue** | A live queue view; "Add to queue" from any song's ⋯ menu. |
| **History** | Plays are recorded and power "Recently played". |
| **Cover art** | Generated on the fly by Flask as gradient SVGs — no image files needed, works offline. |
| **Admin panel** | A separate `/admin` dashboard (admins only): monitoring stats, and add/edit/delete for songs, artists, albums and user accounts. |

> Audio uses royalty-free demo tracks from soundhelix.com, so playback needs an
> internet connection. Everything else works locally.

---

## 🚀 Quick start (Windows + XAMPP)

### 1. Start MySQL
Open the **XAMPP Control Panel** and click **Start** next to **MySQL**.
(Apache is *not* required — Flask serves the site itself.)

### 2. Install the Python packages
From this project folder:

```bash
pip install -r requirements.txt
```

### 3. (Optional) configure the database connection
Defaults already match a stock XAMPP install (`root`, no password,
`127.0.0.1:3306`). To change anything, copy `.env.example` to `.env` and edit it.

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

Open **http://localhost:5000** and log in with the demo account:

```
username:  demo
password:  demo12345
```

…or click **Sign up** to make your own account.

---

## 🛡️ Admin panel

Open **http://localhost:5000/admin** and log in with the admin account:

```
username:  admin
password:  admin12345
```

From there you can:
- **Dashboard** — totals, plays today/this week, top songs, recent activity, genre breakdown
- **Songs / Artists / Albums** — add, edit and delete catalog entries
- **Users** — create accounts, reset passwords, grant/revoke admin, delete users

Admins also get an **"Admin panel"** link in their account menu inside the main app.

> **Upgrading an existing database?** If you set up the project *before* the admin
> feature, run this once to add the `is_admin` column and the admin account
> without wiping your data:
>
> ```bash
> python make_admin.py
> ```
> (Fresh `python seed.py` runs already include the admin account.)

---

## 🗄️ Using phpMyAdmin instead (optional)

If you'd rather create the tables through phpMyAdmin:

1. Open **http://localhost/phpmyadmin**
2. **Import** → choose `schema.sql` → **Go** (creates the DB + tables)
3. Back in the terminal, run `python seed.py` to load the sample data.

---

## 📁 Project structure

```
Elite_Minus/
├── app.py              # App factory + entry point
├── config.py           # Settings (DB connection, secret key)
├── extensions.py       # SQLAlchemy / Bcrypt / Login-Manager singletons
├── models.py           # Database models (users, artists, albums, songs, …)
├── seed.py             # Creates the DB + tables + sample data
├── make_admin.py       # Non-destructive migration: adds admin to an existing DB
├── schema.sql          # Plain-SQL schema for phpMyAdmin (optional)
├── requirements.txt
├── .env.example
├── blueprints/
│   ├── auth.py         # register / login / logout
│   ├── main.py         # serves the single-page app shell
│   ├── api.py          # JSON API (search, playlists, likes, follows, …)
│   └── admin.py        # /admin page + /api/admin/* (dashboard + CRUD)
├── templates/
│   ├── app.html        # the SPA shell (sidebar + player + content)
│   ├── admin.html      # the admin dashboard shell
│   ├── login.html
│   └── register.html
└── static/
    ├── css/styles.css  # scrollbars, sliders, animations
    └── js/
        ├── api.js          # fetch wrapper + helpers
        ├── components.js   # HTML render functions
        ├── player.js       # the audio engine
        ├── app.js          # router + event wiring
        └── admin.js        # admin dashboard controller
```

---

## 🛠️ Tech notes

- **Database:** MySQL/MariaDB via SQLAlchemy with the PyMySQL driver.
- **Auth:** Flask-Login sessions; passwords hashed with Flask-Bcrypt.
- **Frontend:** Tailwind via the Play CDN (no build step). For production you'd
  compile Tailwind with the CLI/PostCSS instead.
- **API:** all dynamic data is served as JSON under `/api/*`.

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
