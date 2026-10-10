import os, re, json, smtplib, hashlib, sys
import certifi
from pathlib import Path
from email.message import EmailMessage
import requests
from bs4 import BeautifulSoup

COURSES = {
 'Open Science Essentials': 'https://stemgateway.nasa.gov/s/course-offering/a0BSJ0000049icD/open-science-essentials',
 'Open Science 101': 'https://stemgateway.nasa.gov/s/course-offering/a0BSJ0000049ih3/open-science-101',
}
STATE = Path('state.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; NASA-Course-Availability-Monitor/1.0)'}
CLOSED = re.compile(r'reached capacity|registration is closed|registration closed|fully booked|no longer accepting applications', re.I)
OPEN = re.compile(r'registration (?:is )?open|applications (?:are )?open|apply now|now accepting applications', re.I)
DATE = re.compile(r'(registration (?:start|end) date.{0,65}|\b\d{1,2}/\d{1,2}/20\d{2}\b)', re.I)

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25, verify=certifi.where())
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    for x in soup(['script', 'style', 'nav', 'footer', 'header']): x.decompose()
    text = ' '.join(soup.stripped_strings)
    # Salesforce pages may render data only in JavaScript; do not misreport an empty shell as available.
    if len(text) < 200 or not re.search(r'open science|registration|course offering', text, re.I):
        raise ValueError('Page content not reliably accessible (possibly JS-rendered).')
    apply = any(a.get_text(' ', strip=True).lower() == 'apply' for a in soup.find_all(['a', 'button']))
    closed = bool(CLOSED.search(text))
    opened = bool(OPEN.search(text)) or apply
    status = 'closed' if closed else ('potentially_open' if opened else 'unknown')
    # Capture opportunity content preferentially; fallback to page body.
    match = re.search(r'about this opportunity(.{0,4500})', text, re.I)
    relevant = match.group(1) if match else text[:4500]
    relevant = re.sub(r'\s+', ' ', relevant).strip()
    return {'status': status, 'apply': apply, 'digest': hashlib.sha256(relevant.encode()).hexdigest(), 'excerpt': relevant[:700], 'dates': DATE.findall(text)[:12]}

def send(subject, body):
    user = os.environ['GMAIL_USER']; password = os.environ['GMAIL_APP_PASSWORD']; to = os.environ['ALERT_EMAIL']
    msg = EmailMessage(); msg['From'] = user; msg['To'] = to; msg['Subject'] = subject; msg.set_content(body)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=25) as smtp:
        smtp.login(user, password); smtp.send_message(msg)

def main():
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    updated = dict(previous)
    alerts = []
    failures = []
    for name, url in COURSES.items():
        try:
            data = fetch(url)
            old = previous.get(name)
            if old:
                if data['status'] == 'potentially_open' and old['status'] != 'potentially_open':
                    alerts.append(f'POSSIBLE REGISTRATION OPEN: {name}\n{url}\n{data["excerpt"]}')
                elif data['digest'] != old['digest'] or data['dates'] != old['dates'] or data['status'] != old['status']:
                    alerts.append(f'NASA COURSE PAGE CHANGED: {name}\nStatus: {data["status"]}\n{url}\n{data["excerpt"]}')
            updated[name] = data
            print(f'{name}: {data["status"]}, apply={data["apply"]}')
        except Exception as exc:
            failures.append(f'{name}: {exc}')
            print(f'ERROR {name}: {exc}', file=sys.stderr)
    if alerts:
        send('NASA course monitor: registration/page update', '\n\n---\n\n'.join(alerts) + '\n\nVerify registration on the NASA website; this is not a confirmed seat.')
    if not previous and updated:
        send('NASA course monitor: initialized', 'Initial check complete. Monitoring:\n' + '\n'.join(f'{k}: {v["status"]}' for k,v in updated.items()) + ('\nErrors:\n'+'\n'.join(failures) if failures else ''))
    if updated != previous:
        STATE.write_text(json.dumps(updated, indent=2) + '\n')
    if failures:
        raise RuntimeError('Some pages could not be monitored. Check logs; no availability claim was made.')

if __name__ == '__main__': main()
