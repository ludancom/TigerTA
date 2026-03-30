#!/usr/bin/env python

#-----------------------------------------------------------------------
# auth.py
#-----------------------------------------------------------------------

import urllib.request
import urllib.parse
import re
import json
import flask
import ssl

# Optional:
import database 

#-----------------------------------------------------------------------

_CAS_URL = 'https://fed.princeton.edu/cas/'

#-----------------------------------------------------------------------
# Authentication routes
#-----------------------------------------------------------------------

def init(app):

    app.add_url_rule('/logoutapp',  'logoutapp', logoutapp,
        methods=['GET'])
    app.add_url_rule('/logoutcas',  'logoutcas', logoutcas,
        methods=['GET'])

#-----------------------------------------------------------------------

# Log out of the application.

def logoutapp():

    username = flask.session['username']

    # Optional:
    database.delete_userinfo(username)

    flask.session.clear()
    return flask.send_file('loggedout.html')

#-----------------------------------------------------------------------

# Log out of the CAS session, and then the application.

def logoutcas():

    logout_url = (_CAS_URL + 'logout?service='
        + urllib.parse.quote(
            re.sub('logoutcas', 'logoutapp', flask.request.url)))
    flask.abort(flask.redirect(logout_url))

#-----------------------------------------------------------------------
# Authentication functions
#-----------------------------------------------------------------------

# Return url after stripping out the "ticket" parameter that was
# added by the CAS server.

def strip_ticket(url):
    if url is None:
        return "something is badly wrong"
    url = re.sub(r'ticket=[^&]*&?', '', url)
    url = re.sub(r'\?&?$|&$', '', url)
    return url

#-----------------------------------------------------------------------

# Validate a login ticket by contacting the CAS server. If
# valid, return the user's user_info; otherwise, return None.

def validate(ticket):
    val_url = (_CAS_URL + "validate"
        + '?service='
        + urllib.parse.quote(strip_ticket(flask.request.url))
        + '&ticket='
        + urllib.parse.quote(ticket)
        + '&format=json')
    
    with urllib.request.urlopen(val_url) as flo:
        result = json.loads(flo.read().decode('utf-8'))

    if (not result) or ('serviceResponse' not in result):
        return None

    service_response = result['serviceResponse']

    if 'authenticationSuccess' in service_response:
        user_info = service_response['authenticationSuccess']
        return user_info

    if 'authenticationFailure' in service_response:
        print('CAS authentication failure:', service_response)
        return None

    print('Unexpected CAS response:', service_response)
    return None

#-----------------------------------------------------------------------

def is_authenticated():

    return 'username' in flask.session

#-----------------------------------------------------------------------

# Optional:
def get_userinfo():

    username = flask.session.get('username')
    return json.loads(database.get_userinfo(username))

#-----------------------------------------------------------------------

def get_username():

    return flask.session.get('username', '')

#-----------------------------------------------------------------------

# Authenticate the user. Do not return unless the user is
# successfully authenticated.

def authenticate():

    # If the username is in the session, then the user was
    # authenticated previously.  So return.
    if flask.session.get('username') is not None:
        return

    # If the request does not contain a login ticket, then redirect
    # the browser to the login page to get one.
    ticket = flask.request.args.get('ticket')
    if ticket is None:
        login_url = (_CAS_URL + 'login?service=' +
            urllib.parse.quote(flask.request.url))
        flask.abort(flask.redirect(login_url))

    # If the login ticket is invalid, then redirect the browser
    # to the login page to get a new one.
    userinfo = validate(ticket)
    if userinfo is None:
        login_url = (_CAS_URL + 'login?service='
            + urllib.parse.quote(strip_ticket(flask.request.url)))
        flask.abort(flask.redirect(login_url))

    # The user is authenticated, so store the username in
    # the session, (optionally) store the userinfo in the database,
    # and return.
    username = userinfo.get('user', '')
    flask.session['username'] = username

    # Optional:
    #database.put_userinfo(username, json.dumps(userinfo))
