#-----------------------------------------------------------------------
# admin.py
#-----------------------------------------------------------------------
""" Flask program that communicates with the Neon database to modify
queue entries. """

import flask
import os
import database
import auth

#-----------------------------------------------------------------------
admin_routes = flask.Blueprint('admin_routes', __name__, template_folder='.')

#-----------------------------------------------------------------------
# Secure Https Use:
#-----------------------------------------------------------------------
@admin_routes.before_request
def before_request():
    is_running_locally = '//localhost:' in flask.request.url_root
    is_using_https = flask.request.is_secure
    if (not is_running_locally) and (not is_using_https):
        url = flask.request.url.replace('http://', 'https://', 1)
        return flask.redirect(url, code=301)
    return None

#-----------------------------------------------------------------------
# Admin Page:
#-----------------------------------------------------------------------
@admin_routes.route('/adminpage', methods=['GET'])
def adminpage():
    """ Method that displays the adminpage to administrators. """

    tas = database.get_all_tas()
    return flask.render_template('adminpage.html', tas=tas)

#-----------------------------------------------------------------------
# Add TA Page:
#-----------------------------------------------------------------------
@admin_routes.route('/add_ta', methods=['POST'])
def add_ta():
    """ Method that adds a TA to the database. """

    ta_net_id = flask.request.form.get('ta_net_id')
    ta_name = flask.request.form.get('ta_name')
    ta_email = f'{ta_net_id}@princeton.edu'
    course = flask.request.form.get('course')

    additionSuccessful = database.add_ta(ta_net_id, ta_name, ta_email, course)
    if additionSuccessful:
        return flask.redirect('/adminpage')
    else:
        return flask.redirect('/adminpage?error=ta_not_added')

#-----------------------------------------------------------------------
# Remove TA Page:
#-----------------------------------------------------------------------
@admin_routes.route('/remove_ta', methods=['POST'])
def remove_ta():
    """ Method that removes a TA from the database. """
    ta_net_id = flask.request.form.get('ta_net_id')

    removeSuccessful = database.remove_ta(ta_net_id)
    if removeSuccessful:
        return flask.redirect('/adminpage')
    else: 
        return flask.redirect('/adminpage?error=ta_not_removed')

#-----------------------------------------------------------------------
# Edit TA Modal:
#-----------------------------------------------------------------------
@admin_routes.route('/edit_ta', methods=['POST'])
def edit_ta():
    """ Method that edits a TA in the database. """

    ta_net_id = flask.request.form.get('ta_netid', '').strip()
    ta_name = flask.request.form.get('ta_name', '').strip()
    ta_email = flask.request.form.get('ta_email', '').strip()
    courses = flask.request.form.get('ta_courses', '').strip()

    database.edit_ta(ta_net_id, ta_name, ta_email, courses)

    return flask.redirect(flask.url_for('admin_routes.adminpage'))