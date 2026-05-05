#-----------------------------------------------------------------------
# app.py
#-----------------------------------------------------------------------
""" Program that initializes the web server and begins our app. """

import flask
import os
import dotenv
import auth
import sys
import argparse
from student import student_routes
from ta import ta_routes
from admin import admin_routes
import flask_wtf.csrf
import notifications

#-----------------------------------------------------------------------
# Create app
app = flask.Flask(
    __name__,
    template_folder='.',
    static_folder='.',
    static_url_path='/static'
)

#-----------------------------------------------------------------------
# CAS Authentication
dotenv.load_dotenv()
_APP_SECRET_KEY = os.getenv('APP_SECRET_KEY')
app.secret_key = _APP_SECRET_KEY

# Mail config. .strip() guards against trailing whitespace in either
# the local .env file or Render's environment panel, which silently
# breaks DNS / SMTP AUTH.
def _envstr(name, default=None):
    raw = os.getenv(name, default)
    return raw.strip() if isinstance(raw, str) else raw

app.config['MAIL_SERVER'] = _envstr('MAIL_SERVER')
app.config['MAIL_PORT'] = int(_envstr('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = (_envstr('MAIL_USE_TLS', 'True') or '').lower() == 'true'
app.config['MAIL_USERNAME'] = _envstr('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = _envstr('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = _envstr('MAIL_DEFAULT_SENDER')

notifications.mail.init_app(app)
auth.init(app)

# Security Measures
flask_wtf.csrf.CSRFProtect(app)


#-----------------------------------------------------------------------
# /diagnose route: temporary debugging endpoint that runs a step-by-step
# SMTP test from inside the running container and returns the result as
# plain text. Lets us see what's failing without needing log access.
# Remove this route once email is confirmed working in production.
#-----------------------------------------------------------------------
import socket
import time
import traceback as _traceback
from flask_mail import Message as _DiagMessage

@app.route('/diagnose')
def _diagnose():
    lines = []
    def log(s):
        lines.append(s)

    server = app.config.get('MAIL_SERVER') or ''
    port = app.config.get('MAIL_PORT') or 587
    username = app.config.get('MAIL_USERNAME') or ''
    password = app.config.get('MAIL_PASSWORD') or ''
    sender = app.config.get('MAIL_DEFAULT_SENDER') or ''

    log("=== TigerTA SMTP diagnostic ===")
    log(f"server   = {server!r}")
    log(f"port     = {port}")
    log(f"use_tls  = {app.config.get('MAIL_USE_TLS')}")
    log(f"username = {username!r}")
    log(f"sender   = {sender!r}")
    log(f"password = <{len(password)} chars>")
    log("")

    log("[1/4] DNS lookup for the mail server...")
    try:
        addrs = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
        log(f"      OK: resolves to {addrs[0][4]}")
    except Exception as ex:
        log(f"      FAIL: {type(ex).__name__}: {ex}")
        return ("\n".join(lines), 200, {'Content-Type': 'text/plain'})

    log("[2/4] Raw TCP connect (5s timeout)...")
    t0 = time.time()
    try:
        sock = socket.create_connection((server, port), timeout=5)
        sock.close()
        log(f"      OK: connected in {time.time() - t0:.2f}s")
    except Exception as ex:
        log(f"      FAIL after {time.time() - t0:.2f}s: {type(ex).__name__}: {ex}")
        log("")
        log("      => This means the host running TigerTA cannot reach the SMTP")
        log("         server on this port. On Render free/hobby/starter plans,")
        log("         outbound 25/465/587 is blocked. Switch to an HTTP email API")
        log("         (Resend, SendGrid, Mailgun) or upgrade Render.")
        return ("\n".join(lines), 200, {'Content-Type': 'text/plain'})

    log("[3/4] Reachability to general internet (sanity check)...")
    t0 = time.time()
    try:
        sock = socket.create_connection(('1.1.1.1', 443), timeout=5)
        sock.close()
        log(f"      OK: 1.1.1.1:443 connect in {time.time() - t0:.2f}s")
    except Exception as ex:
        log(f"      FAIL: {type(ex).__name__}: {ex}")

    log("[4/4] Trying flask_mail.send() to ak1225@princeton.edu (10s timeout)...")
    old_to = socket.getdefaulttimeout()
    socket.setdefaulttimeout(10)
    try:
        msg = _DiagMessage(
            subject="[TigerTA] /diagnose test",
            recipients=["ak1225@princeton.edu"],
        )
        msg.body = "If you got this, /diagnose says SMTP works end-to-end."
        notifications.mail.send(msg)
        log("      OK: send() returned without exception")
        log("")
        log(">>> Check ak1225@princeton.edu (inbox + spam).")
    except Exception as ex:
        log(f"      FAIL: {type(ex).__name__}: {ex}")
        log("")
        log("Full traceback:")
        log(_traceback.format_exc())
    finally:
        socket.setdefaulttimeout(old_to)

    return ("\n".join(lines), 200, {'Content-Type': 'text/plain'})


# Register routes
app.register_blueprint(student_routes)
app.register_blueprint(ta_routes)
app.register_blueprint(admin_routes)

#-----------------------------------------------------------------------
# Run Server
def main():
    parser = argparse.ArgumentParser(description=
    "COS Lab TA Queue Application")
    parser.add_argument("port",type=int,
    help= "the port at which the server should listen")

    args = parser.parse_args()

    try:
        app.run(host='0.0.0.0', port=args.port, debug=True)
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()