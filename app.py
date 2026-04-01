#-----------------------------------------------------------------------
# app.py
#-----------------------------------------------------------------------
import flask
import os
import dotenv
import auth
import sys
import argparse
from student import student_routes
from ta import ta_routes

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
auth.init(app)

#-----------------------------------------------------------------------
# register routes
app.register_blueprint(student_routes)
app.register_blueprint(ta_routes)

#-----------------------------------------------------------------------
# running

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