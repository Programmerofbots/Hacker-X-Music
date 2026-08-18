<h1 align="center"><b>[⚡] 𝐇𝐀𝐂𝐊𝐄𝐑 𝐗 𝐌𝐔𝐒𝐈𝐂 [⚡]</b></h1>

<h4 align="center"> 𝐀 𝐏𝐎𝐖𝐄𝐑𝐅𝐔𝐋 𝐇𝐀𝐂𝐊𝐄𝐑 𝐗 𝐌𝐔𝐒𝐈𝐂 𝐁𝐎𝐓</h4>

<p align="center"><a href="https://t.me/legend_of_all_groups"><img src="https://te.legra.ph/file/52792e7acc085c69eeb14.jpg" width="400"></a></p>

> ⭐️ Thanks to everyone for using **𝐇𝐀𝐂𝐊𝐄𝐑 𝐗 𝐌𝐔𝐒𝐈𝐂**!

---

## 📋 Table of Contents
- [Requirements / Prerequisite](#-requirements)
- [Deploy on VPS (Step by Step)](#-deploy-on-vps-recommended)
  - [Method 1: Manual Setup with screen (24/7 Running)](#method-1-manual-setup-using-screen-recommended)
  - [Method 2: Quick Automated Setup](#method-2-quick-setup-using-setup-script)
  - [Method 3: Systemd Service (Auto-Start on Boot)](#method-3-systemd-service-auto-restart--boot)
  - [Method 4: Deploy with Docker](#method-4-deploy-with-docker)
- [Deploy on Heroku](#-deploy-on-heroku)
- [Environment Variables (.env)](#-environment-variables-setup)
- [Support & Community](#-support)

---

## 🛠 Requirements

Before deploying, ensure you have:
1. **Linux VPS** (Ubuntu 20.04 / 22.04 / 24.04 or Debian recommended).
2. **API_ID & API_HASH** — Obtain from [my.telegram.org](https://my.telegram.org).
3. **BOT_TOKEN** — Obtain from [@BotFather](https://t.me/BotFather).
4. **MONGO_DB_URI** — MongoDB database connection string from [MongoDB Atlas](https://www.mongodb.com/).
5. **STRING_SESSION** — Pyrogram v2 String Session (generate using string generator bot or script).
6. **OWNER_ID** — Your Telegram User ID (get from [@MissRose_bot](https://t.me/MissRose_bot) using `/id`).
7. **LOGGER_ID** — Telegram Group/Channel ID (with `-100...`) where bot logs events.

---

## 🚀 Deploy on VPS (Recommended)

### Method 1: Manual Setup using `screen` (Recommended)

#### Step 1: Connect to your VPS and Update Packages
Open your terminal (PuTTY / SSH) and run:
```bash
sudo apt update && sudo apt upgrade -y
```

#### Step 2: Install Required Dependencies (Python, Pip, FFmpeg, Git, Screen)
```bash
sudo apt install git python3 python3-pip ffmpeg screen -y
```

#### Step 3: Clone the Repository
```bash
git clone https://github.com/bindplant123/Hacker-X-Music.git
cd Hacker-X-Music
```

#### Step 4: Install Python Requirements
```bash
pip3 install -U pip
pip3 install -U -r requirements.txt
```

#### Step 5: Configure Environment Variables
Create and edit your `.env` file:
```bash
cp sample.env .env
nano .env
```
Fill in your details:
```env
API_ID=1234567
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
LOGGER_ID=-1001234567890
MONGO_DB_URI=your_mongodb_connection_string
OWNER_ID=your_telegram_id
STRING_SESSION=your_pyrogram_string_session
```
> **Tip:** Save and exit `nano` by pressing `CTRL + O`, then `Enter`, then `CTRL + X`.

#### Step 6: Start Bot in Background (24/7 Online)
Create a new screen session:
```bash
screen -S musicbot
```
Start the bot inside the screen:
```bash
python3 -m AnonXMusic
```
- **To Detach screen (keep running in background):** Press `CTRL + A` then `D`.
- **To Reattach screen (check live logs):** Run `screen -r musicbot`.
- **To Stop the bot:** Inside screen, press `CTRL + C`.

---

### Method 2: Quick Setup using `setup` Script

1. **Update and install git:**
   ```bash
   sudo apt update && sudo apt install git screen -y
   ```
2. **Clone & run installer:**
   ```bash
   git clone https://github.com/bindplant123/Hacker-X-Music.git
   cd Hacker-X-Music
   bash setup
   ```
3. Enter your `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `MONGO_DB_URI`, `LOGGER_ID`, and `STRING_SESSION` when prompted.
4. **Run the bot:**
   ```bash
   screen -S musicbot
   bash start
   ```
   *(Press `CTRL + A` then `D` to detach)*

---

### Method 3: Systemd Service (Auto-Restart & Boot)

To ensure your bot restarts automatically if VPS reboots or if it crashes:

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/musicbot.service
   ```
2. Paste the following configuration (replace `YOUR_USERNAME` with your VPS username, e.g. `root` or `ubuntu`):
   ```ini
   [Unit]
   Description=Hacker-X-Music Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/Hacker-X-Music
   ExecStart=/usr/bin/python3 -m AnonXMusic
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Reload daemon and start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable musicbot
   sudo systemctl start musicbot
   ```
4. **Service Management Commands:**
   - Check status / logs: `sudo systemctl status musicbot`
   - Restart bot: `sudo systemctl restart musicbot`
   - Stop bot: `sudo systemctl stop musicbot`
   - View live logs: `journalctl -u musicbot -f`

---

### Method 4: Deploy with Docker

1. **Install Docker:**
   ```bash
   sudo apt update && sudo apt install docker.io -y
   ```
2. **Clone repository and configure `.env`:**
   ```bash
   git clone https://github.com/bindplant123/Hacker-X-Music.git
   cd Hacker-X-Music
   cp sample.env .env
   nano .env
   ```
3. **Build and Run Docker Container:**
   ```bash
   docker build -t hacker-x-music .
   docker run -d --name musicbot --restart always --env-file .env hacker-x-music
   ```
4. **Manage Docker Container:**
   - View logs: `docker logs -f musicbot`
   - Restart: `docker restart musicbot`
   - Stop: `docker stop musicbot`

---

## ⚙️ Environment Variables Setup

| Variable | Description | Mandatory |
| :--- | :--- | :---: |
| `API_ID` | Telegram API ID from [my.telegram.org](https://my.telegram.org) | **Yes** |
| `API_HASH` | Telegram API HASH from [my.telegram.org](https://my.telegram.org) | **Yes** |
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) | **Yes** |
| `OWNER_ID` | Telegram user ID of bot owner | **Yes** |
| `MONGO_DB_URI` | MongoDB database URI string | **Yes** |
| `LOGGER_ID` | Log channel/group ID (starts with `-100`) | **Yes** |
| `STRING_SESSION` | Pyrogram v2 string session for assistant account | **Yes** |
| `COOKIES_DIR` | Directory containing `cookies*.txt` pool (Default: `.`) | No |
| `YOUTUBE_API_KEY`| Google Cloud YouTube Data API v3 key (Faster search) | No |

---

## ☁️ Deploy on Heroku

<h3 align="center">
    ─「 𝐃𝐄𝐏𝐋𝐎𝐘 𝐎𝐍 𝐇𝐄𝐑𝐎𝐊𝐔 」─
</h3>

<p align="center">
  <a href="https://dashboard.heroku.com/new?template=https://github.com/bindplant123/Hacker-X-Music">
    <img src="https://img.shields.io/badge/Deploy%20On%20Heroku-black?style=for-the-badge&logo=heroku" width="220" height="38.45"/>
  </a>
</p>

<details>
<summary><b>Click to Deploy to Heroku</b></summary>
<br>

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://dashboard.heroku.com/new?template=https://github.com/bindplant123/Hacker-X-Music)

</details>

---

## 💬 Support

<details>
<summary><b>Join Support & Updates Channel</b></summary>
<br>

<a href="https://t.me/O_P_Hacker"><img src="https://img.shields.io/badge/Join-Telegram%20Channel-red.svg?logo=Telegram"></a>
<a href="https://t.me/legend_of_all_groups"><img src="https://img.shields.io/badge/Join-Support%20Group-blue.svg?logo=Telegram"></a>

</details>
