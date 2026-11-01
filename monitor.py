import os, re, json, smtplib, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path
from email.message import EmailMessage
from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeout

COURSES = {
 'Open Science Essentials': 'https://stemgateway.nasa.gov/s/course-offering/a0BSJ0000049icD/open-science-essentials',
 'Open Science 101': 'https://stemgateway.nasa.gov/s/course-offering/a0BSJ0000049ih3/open-science-101',
}
STATE = Path('state.json')
STATUS_LABELS = {'closed': 'Closed', 'potentially_open': 'POSSIBLY OPEN (Apply button visible)', 'unknown': 'Unknown'}
HEARTBEAT_WEEKDAY, HEARTBEAT_HOUR = 5, 8  # weekly "still working" email: first run on Saturday from 08:00 UTC
CLOSED = re.compile(r'reached capacity|registration is closed|registration closed|fully booked|no longer accepting applications', re.I)
OPEN = re.compile(r'registration (?:is )?open|applications (?:are )?open|apply now|now accepting applications', re.I)
DATE = re.compile(r'(registration (?:start|end) date.{0,65}|\b\d{1,2}/\d{1,2}/20\d{2}\b)', re.I)
# STEM Gateway is a Salesforce site: the static HTML is an empty "Loading" shell and the course
# details are rendered by JavaScript, so pages are loaded in a real (headless) browser.
RENDERED = "/about this opportunity|registration start date/i.test(document.body.innerText)"

def launch(p):
    # Prefer the Google Chrome already installed on GitHub runners; fall back to Playwright's Chromium.
    try:
        return p.chromium.launch(channel='chrome')
    except PlaywrightError:
        return p.chromium.launch()

def fetch(page, url):
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_function(RENDERED, timeout=45000)
        # The Apply button is rendered by a separate component after the details; let requests settle.
        page.wait_for_load_state('networkidle', timeout=15000)
    except PlaywrightTimeout:
        pass
    text = ' '.join(page.locator('body').inner_text().split())
    # Do not misreport an unrendered/blocked page as available.
    if len(text) < 200 or not re.search(r'about this opportunity|registration start date', text, re.I):
        raise ValueError('Page content not reliably accessible (did not finish rendering).')
    # The Apply button lives inside the header component's shadow DOM; Playwright locators pierce it.
    apply = page.get_by_role('button', name='Apply', exact=True).or_(page.get_by_role('link', name='Apply', exact=True)).count() > 0
    closed = bool(CLOSED.search(text))
    opened = bool(OPEN.search(text))
    # An Apply button is the strongest signal; the "registration is closed" notice may linger after it reopens.
    status = 'potentially_open' if apply else ('closed' if closed else ('potentially_open' if opened else 'unknown'))
    # Capture opportunity content preferentially; fallback to page body.
    match = re.search(r'about this opportunity(.{0,4500})', text, re.I)
    relevant = (match.group(1) if match else text[:4500]).strip()
    return {'status': status, 'apply': apply, 'digest': hashlib.sha256(relevant.encode()).hexdigest(), 'excerpt': relevant[:700], 'dates': DATE.findall(text)[:12]}

def send(subject, body, to):
    user = os.environ['GMAIL_USER']; password = os.environ['GMAIL_APP_PASSWORD']
    msg = EmailMessage(); msg['From'] = user; msg['To'] = ', '.join(to); msg['Subject'] = subject; msg.set_content(body)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=25) as smtp:
        smtp.login(user, password); smtp.send_message(msg)

def status_summary(state):
    return '\n'.join(f'- {name}: {STATUS_LABELS[state[name]["status"]]}' for name in COURSES if name in state)

def main():
    yana = os.environ['ALERT_EMAIL']  # status changes go to Yana
    # The weekly "still working" email goes to Yana and to the sending account (the repo owner).
    heartbeat_recipients = list(dict.fromkeys([os.environ['GMAIL_USER'], yana]))
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    updated = dict(previous)
    alerts = []
    failures = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        for name, url in COURSES.items():
            try:
                data = fetch(page, url)
                old = previous.get(name)
                # Only a status change (closed / possibly open / unknown) triggers an email; text edits do not.
                if old and data['status'] != old['status']:
                    alerts.append(f'{name}\nStatus: {STATUS_LABELS[old["status"]]} -> {STATUS_LABELS[data["status"]]}\n{url}\n\n{data["excerpt"]}')
                updated[name] = data
                print(f'{name}: {data["status"]}, apply={data["apply"]}')
            except Exception as exc:
                failures.append(f'{name}: {exc}')
                print(f'ERROR {name}: {exc}', file=sys.stderr)
        browser.close()
    if alerts:
        opened = any(updated[name]['status'] == 'potentially_open' for name in COURSES if name in updated)
        subject = 'NASA course registration may be OPEN' if opened else 'NASA course status changed'
        send(subject, '\n\n---\n\n'.join(alerts) + '\n\nVerify registration on the NASA website; this is not a confirmed seat.', [yana])
    if not previous and updated:
        send('NASA course monitor: initialized', 'Initial check complete. Monitoring:\n' + status_summary(updated) + ('\nErrors:\n'+'\n'.join(failures) if failures else ''), [yana])
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if now.weekday() == HEARTBEAT_WEEKDAY and now.hour >= HEARTBEAT_HOUR and previous.get('last_heartbeat') != today:
        body = (f'The NASA course monitor is still running (checked {now:%Y-%m-%d %H:%M} UTC).\n\nCurrent status:\n'
                + status_summary(updated) + ('\n\nErrors this run:\n' + '\n'.join(failures) if failures else ''))
        try:
            send('NASA course monitor: still working', body, heartbeat_recipients)
            updated['last_heartbeat'] = today
        except Exception as exc:
            failures.append(f'Weekly email: {exc}')
            print(f'ERROR weekly email: {exc}', file=sys.stderr)
    if updated != previous:
        STATE.write_text(json.dumps(updated, indent=2) + '\n')
    if failures:
        raise RuntimeError('Some pages could not be monitored. Check logs; no availability claim was made.')

if __name__ == '__main__': main()
