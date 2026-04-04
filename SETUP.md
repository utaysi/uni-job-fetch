# Server Setup

## 1. Install dependencies

```bash
sudo apt update
sudo apt install -y curl python3 pdfgrep
```

## 2. Deploy the project

```bash
mkdir -p ~/uni-job-fetch
# copy fetch-jobs.sh and run-scheduled.sh to ~/uni-job-fetch/
chmod +x ~/uni-job-fetch/fetch-jobs.sh ~/uni-job-fetch/run-scheduled.sh
```

## 3. Configure ntfy topic

Edit `run-scheduled.sh` and replace `uni-jobs-ruby-XXXX` with your chosen topic name:

```bash
nano ~/uni-job-fetch/run-scheduled.sh
```

Install the [ntfy app](https://ntfy.sh) on your phone and subscribe to the same topic.

## 4. Test manually

```bash
cd ~/uni-job-fetch
./fetch-jobs.sh --notify YOUR_TOPIC --cleanup
```

## 5. Install systemd units

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/uni-job-fetch.service << 'EOF'
[Unit]
Description=Uni Marburg Job Fetcher
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=%h/uni-job-fetch/run-scheduled.sh
EOF

cat > ~/.config/systemd/user/uni-job-fetch.timer << 'EOF'
[Unit]
Description=Run Uni Job Fetcher every 15 minutes

[Timer]
OnCalendar=*:00,15,30,45
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

## 6. Enable the timer

```bash
systemctl --user daemon-reload
systemctl --user enable --now uni-job-fetch.timer
```

User lingering must be enabled so the timer runs when you're not logged in:

```bash
sudo loginctl enable-linger $USER
```

## 7. Verify

```bash
systemctl --user list-timers
systemctl --user start uni-job-fetch.service   # test run
journalctl --user -u uni-job-fetch -f           # watch logs
```
