# NASA Course Monitor v2

Monitors the **specific NASA STEM Gateway offering pages** for Open Science Essentials and Open Science 101. Alerts on changes to visible opportunity text, registration dates, and potential registration opening. It does **not** automatically enroll you or guarantee availability. It does not discover new offering IDs.

## Setup

1. Create a **public** GitHub repository named `nasa-course-monitor`.
2. Upload `monitor.py`, `requirements.txt`, and `.github/workflows/monitor.yml` (preserve folders). Do not upload your credentials.
3. Enable Gmail two-step verification, then create an App Password at https://myaccount.google.com/apppasswords .
4. In GitHub repository **Settings > Secrets and variables > Actions**, add repository secrets: `GMAIL_USER` (sending Gmail address), `GMAIL_APP_PASSWORD` (16-character App Password), `ALERT_EMAIL` (destination Gmail address).
5. In **Settings > Actions > General > Workflow permissions**, select **Read and write permissions** and save.
6. In **Actions > NASA course monitor > Run workflow**, run manually. Check logs. An initialization email is sent if at least one page was parsed.
7. Confirm later scheduled runs and email delivery. In Gmail, enable notifications for this sender.

## Limitations

NASA STEM Gateway may render content via JavaScript, require sign-in, or block automated requests. In that case, the script **fails closed**, reports an error in Actions, and cannot monitor availability until adapted to an accessible official data source or a browser-based method. It deliberately does not claim that registration is open from an inaccessible page. If no content is accessible, you may receive no initialization email. GitHub scheduled jobs can be delayed/dropped and public-repo scheduled workflows may be disabled after 60 days of inactivity. GitHub Actions cannot guarantee instant notifications. The program monitors **page changes**, not confirmed live instructor-led availability.

For a safe test, manually run the workflow and review the `Check course pages and email changes` step. If you see `Page content not reliably accessible`, send that error (without secrets) for troubleshooting.
