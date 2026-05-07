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
from werkzeug.middleware.proxy_fix import ProxyFix

#-----------------------------------------------------------------------
# Create app
app = flask.Flask(
    __name__,
    template_folder='.',
    static_folder='.',
    static_url_path='/static'
)

# fix for "too many redirects" on render
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
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