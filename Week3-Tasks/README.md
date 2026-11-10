# Email Sender Bot

A Python script that sends **personalised emails with attachments** to a list of
recipients from a CSV file, using **Gmail SMTP** (`smtplib` + `email`).
Built for things like report distribution and alerting scripts.

## Features

- 📋 **Recipients from CSV** — every column becomes a `{placeholder}` for the subject and body
- ✉️ **Personalised messages** — e.g. `Hi {name}, your report for {company} is attached`
- 📎 **Attachments** — one or more files, MIME type detected automatically
- 🔁 **Retry logic** — failed sends retry with back-off; dropped connections are re-established automatically
- 🧾 **Send-status logging** — `send_status.csv` report + `email_bot.log` for every run
- 🔐 **Secure credentials** — Gmail App Password via environment variables / `.env` / hidden prompt. Never hard-coded
- 🧪 **Dry-run mode** — validate the whole batch without sending a single email

## Requirements

- **Python 3.9 or newer** — that's it. No third-party packages (standard library only), so `requirements.txt` is intentionally empty of dependencies.
- A **Gmail account** with 2-Step Verification and an **App Password** (below).

Check your Python version:

```bash
python --version        # or: python3 --version
```

## Step 1 — Create a Gmail App Password (important)

Gmail does **not** allow your normal account password for scripts. You need an
App Password:

1. Turn on **2-Step Verification**: Google Account → *Security* → *2-Step Verification*.
2. Go to **App passwords**: Google Account → *Security* → *App passwords*
   (or visit `myaccount.google.com/apppasswords`).
3. Give it a name (e.g. `Email Sender Bot`) and click **Create**.
4. Google shows a **16-character password** like `abcd efgh ijkl mnop` — copy it.
   It is shown **only once**.

> ⚠️ Treat the App Password like your real password. Never commit it to Git,
> never paste it into the code, and revoke it from the same page if it leaks.

## Step 2 — Configure your credentials

Pick **one** of these:

**Option A — `.env` file (easiest)**
Copy the example and fill it in:

```bash
cp .env.example .env
```

```ini
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

**Option B — environment variables**

```bash
# Linux / macOS
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"
```

```powershell
# Windows PowerShell
$env:GMAIL_ADDRESS="you@gmail.com"
$env:GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"
```

**Option C — type them when asked.** If nothing is set, the script prompts for
the address and asks for the App Password with hidden input.

## Step 3 — Prepare your files

**`recipients.csv`** — must have an `email` column. Add any extra columns you
want as placeholders:

```csv
email,name,company
ahmed.khan@example.com,Ahmed Khan,TechZone Ltd
sara.ali@example.com,Sara Ali,Bright Marketing
```

**`message.txt`** — the email body. Use `{column}` placeholders matching the CSV:

```text
Hi {name},

Your weekly report for {company} is attached to this email.

Best regards,
Reports Team
```

## Step 4 — Run it

**Always dry-run first** (sends nothing, validates everything):

```bash
python email_sender_bot.py --dry-run \
    --subject "Your weekly report, {name}" \
    --attach sample_report.txt
```

**Test with real sends to just 2 people:**

```bash
python email_sender_bot.py --limit 2 \
    --subject "Your weekly report, {name}" \
    --attach sample_report.txt
```

**Full run with a real attachment:**

```bash
python email_sender_bot.py \
    --recipients recipients.csv \
    --subject "Your weekly report, {name}" \
    --template message.txt \
    --attach report.pdf
```

Multiple attachments: repeat the flag — `--attach report.pdf --attach chart.png`.

## Command-line options

| Flag | Default | What it does |
|---|---|---|
| `--recipients` | `recipients.csv` | CSV file with an `email` column |
| `--subject` | *(required)* | Subject line, supports `{placeholders}` |
| `--template` | `message.txt` | Body template file, supports `{placeholders}` |
| `--attach FILE` | none | Attach a file (repeat for several) |
| `--from-name` | none | Sender display name, e.g. `"Reports Team"` |
| `--delay` | `2.0` | Seconds between sends |
| `--retries` | `3` | Max attempts per recipient |
| `--starttls` | off | Use port 587 + STARTTLS instead of 465 SSL |
| `--limit N` | all | Only process the first N recipients |
| `--dry-run` | off | Validate and log, but send nothing |

## Output files

| File | Contents |
|---|---|
| `send_status.csv` | One row per recipient: `timestamp, email, status (SENT / FAILED / SKIPPED / DRY_RUN), attempts, detail` |
| `email_bot.log` | Full run log (also printed to the console) |

Exit codes: `0` = everything sent, `1` = setup/config error, `2` = finished but some sends failed (see the status CSV).

## Gmail limits & good practice

- Free Gmail accounts can send roughly **500 emails/day**; Google Workspace about **2,000/day**. The bot can't bypass this — keep batches reasonable and keep the default `--delay`.
- Only email people who expect to hear from you (customers, your team, subscribers). Mass unsolicited mail gets accounts flagged fast.
- Authentication errors are deliberately **not** retried — check the App Password instead.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Authentication failed` / `Username and Password not accepted` | You're using your normal password, or 2-Step Verification is off. Create an App Password (Step 1). |
| `Connection problem` retries | Check your internet/firewall; port 465 (or 587 with `--starttls`) must be allowed out. |
| Rows show `SKIPPED` | The `email` value in that CSV row is blank or not a valid address. |
| `{name}` appears literally in a sent email | That CSV row has no matching column — placeholder names must match CSV headers exactly. |
| Attachment error at startup | The `--attach` path is wrong or the file doesn't exist. |

## Project structure

```
email-sender-bot/
├── email_sender_bot.py   # the bot (only file you need to run)
├── recipients.csv        # sample recipient list - replace with yours
├── message.txt           # sample body template
├── sample_report.txt     # demo attachment for testing --attach
├── .env.example          # copy to .env and fill in your credentials
├── requirements.txt      # no dependencies - standard library only
└── README.md             # this file
```

*Generated outputs (not in the repo): `send_status.csv`, `email_bot.log`, `.env`.*
