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
    return flask.render_template('adminpage.html')

#-----------------------------------------------------------------------
# Add TA Page:
#-----------------------------------------------------------------------

@admin_routes.route('/add_ta', methods=['GET', 'POST'])
def add_ta():
    """ Method that adds a TA to the database. """

    if flask.request.method == 'POST':
        ta_net_id = flask.request.form.get('ta_net_id')
        ta_name = flask.request.form.get('ta_name')
        course = flask.request.form.get('course')
        database.add_ta(ta_net_id, ta_name, course)
        return flask.redirect('/view_tas')

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
        return flask.redirect('/view_tas')

    return flask.render_template('remove_ta.html')

#-----------------------------------------------------------------------
# Edit TA Modal:
#-----------------------------------------------------------------------

@admin_routes.route('/edit_ta', methods=['POST'])
def edit_ta():
    """ Method that edits a TA in the database. """

    if flask.request.method == 'POST':
        ta_net_id = flask.request.form.get('ta_net_id')
        ta_name = flask.request.form.get('ta_name')
        course = flask.request.form.get('course')
        database.edit_ta(ta_net_id, ta_name, course)
        return flask.redirect('/view_tas')

    return flask.render_template('edit_ta.html')

#-----------------------------------------------------------------------
# View TAs Page: i dont think we need this?
#-----------------------------------------------------------------------

@admin_routes.route('/view_tas', methods=['GET'])
def view_tas():
    """ Method that displays the list of TAs to the user. """
    tas = database.get_all_tas()
    return flask.render_template('view_tas.html', tas=tas)