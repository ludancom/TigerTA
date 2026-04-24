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
# New workflow needs this
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

@admin_routes.route('/add_ta', methods=['GET', 'POST'])
def add_ta():
    if flask.request.method == 'POST':
        ta_net_id = flask.request.form.get('ta_net_id')
        ta_name = flask.request.form.get('ta_name')
        ta_email = f'{ta_net_id}@princeton.edu'
        course = flask.request.form.get('course')
        database.add_ta(ta_net_id, ta_name, ta_email, course)
        return flask.redirect('/adminpage')
    return flask.render_template('add_ta.html')

#-----------------------------------------------------------------------
# Remove TA Page:
#-----------------------------------------------------------------------

@admin_routes.route('/remove_ta', methods=['GET', 'POST'])
def remove_ta():
    """ Method that removes a TA from the database. """

    if flask.request.method == 'POST':
        ta_net_id = flask.request.form.get('ta_net_id')
        database.remove_ta(ta_net_id)
        return flask.redirect('/adminpage')

    return flask.render_template('remove_ta.html')

#-----------------------------------------------------------------------
# Edit TA Modal:
#-----------------------------------------------------------------------

@admin_routes.route('/edit_ta', methods=['POST'])
def edit_ta():
    """ Method that edits a TA in the database. """

    ta_net_id = flask.request.form.get('ta_netid', '').strip()
    ta_name = flask.request.form.get('ta_name', '').strip()
    ta_email = f'{ta_net_id}@princeton.edu'
    courses = flask.request.form.get('ta_courses', '').strip()

    database.edit_ta(ta_net_id, ta_name, ta_email, courses)

    return flask.redirect(flask.url_for('admin_routes.adminpage'))

#-----------------------------------------------------------------------
# View TAs Page: 
#-----------------------------------------------------------------------

@admin_routes.route('/view_tas', methods=['GET'])
def view_tas():
    """ Method that displays the list of TAs to the user. """
    tas = database.get_all_tas()
    return flask.render_template('view_tas.html', tas=tas)