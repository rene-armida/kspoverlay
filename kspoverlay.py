from datetime import datetime
import json
import tomllib
from traceback import print_exc

from flask import Flask, flash, g, render_template, redirect, request

from models import *

app = Flask(__name__)
# load config, let exceptions propagate
# this doesn't work:
# app.config.from_file("config.toml", load=tomllib.load, text=False)
with open('config.toml', 'rb') as config_fp:
    app.config.update(tomllib.load(config_fp))

# avoid db concurrency errors
# see https://www.iditect.com/faq/python/using-sqlalchemy-session-from-flask-raises-quotsqlite-objects-created-in-a-thread-can-only-be-used-in-that-same-threadquot.html


@app.before_request
def before_request():
    # run the db connection just to get the app to create a sessionmaker
    get_db()
    g.session = g.sessionmaker()

@app.after_request
def after_request(response):
    if hasattr(g, 'session'):
        g.session.close()
    return response

# template filters

@app.template_filter()
def ktime(tval):
    return KTimestamp(tval).as_datetime()

@app.template_filter()
def kinterval(tval):
    return KTimestamp(tval).as_interval()

# routes

@app.route("/")
def index():
    return redirect(f'/admin/mission')

@app.route("/admin/mission")
def admin_mission_list():
    return render_template('admin_mission.html', missions=Mission.by_start())

@app.route("/admin/mission/_new", methods=["GET", "POST"])
def admin_mission_new():
    if request.method == 'POST':
        vals = request.form.copy()
        vals['start'] = KTimestamp.parse(vals['start'])
        errors = False
        if not vals['name']:
            flash('Invalid name', 'error')
            errors = True
        if not vals['start']:
            flash('Invalid start date, use YxxDxx H:MM:SS')
            errors = True

        if not errors:
            try:
                mission = Mission(vals)
                mission.save()
                flash('success', 'info')
                return redirect(f'/admin/mission')
            except ValidationError as exc:
                flash(exc.message, 'error')
    return render_template('admin_mission_editor.html')

@app.route("/admin/mission/<mission_uuid>")
def admin_mission_edit():
    mission = Mission.find_one(uuid=mission_uuid)
    if not mission:
        return ('', 404)
    return render_template('mission_edit.html', mission=mission)

@app.route("/overlay/standby")
def standby():
    return render_template('standby.html')

@app.route("/overlay/flight")
def flight():
    args = {
        'ut': 14322,
        'clock': 'run',
        'missions': {
            'name': "Lond III",
            'priority': 10,
            'last_update': 12355,
            'start': 2031,
        }
    }
    if 'scale' in request.args:
        args['scale'] = request.args['scale']
    return render_template('flight.html', **args)

@app.route("/matcher")
def matcher_list():
    return [matcher.as_json_dict() for matcher in Matcher.iter_all()]

@app.route("/matcher", methods=["POST"])
def matcher_post():
    matcher = Matcher(request.json)
    matcher.save()
    return redirect(f'/matcher/{matcher.uuid}')

@app.route("/matcher/<matcher_uuid>", methods=["GET"])
def matcher_get(matcher_uuid):
    matcher = Matcher.find_one(uuid=matcher_uuid)
    if not matcher:
        return ('', 404)
    return matcher.as_json_dict()

@app.route("/matcher/<matcher_uuid>", methods=["DELETE"])
def matcher_delete(matcher_uuid):
    matcher = Matcher.find_one(uuid=matcher_uuid)
    matcher.delete()
    return ('', 200)

@app.route("/mission")
def mission_list():
    return [mission.as_json_dict() for mission in Mission.iter_all()]

@app.route("/mission", methods=["POST"])
def mission_post():
    Mission(request.json).save()
    m = Mission.find_one(name=request.json['name'])
    return redirect(f'/mission/{m.uuid}')

@app.route("/mission/<mission_uuid>", methods=["GET"])
def mission_get(mission_uuid):
    mission = Mission.find_one(uuid=mission_uuid)
    if not mission:
        return ('', 404)
    return mission.as_json_dict()

@app.route("/mission/<mission_uuid>", methods=["PUT"])
def mission_put(mission_uuid):
    Mission(request.json()).save()
    return ('', 200)

@app.route("/mission/<mission_uuid>", methods=["DELETE"])
def mission_delete(mission_uuid):
    m1 = Mission.find_one(uuid=mission_uuid)
    m1.delete()
    return ('', 200)


@app.route("/update", methods=["POST"])
def update_post():
    try:
        update = Update.from_json(request.json)
    except Exception as exc:
        with open(app.config['bad_request_log'], 'a') as log_fp:
            # log_fp.write(str(exc) + '\n')
            log_fp.write(f'BAD REQUEST, CLIENT TIME: {datetime.now():%c}\n')
            json.dump(request.json, log_fp, indent=2)
            log_fp.write('\n')
            print_exc(file=log_fp)

        msg = f'Invalid update data. {exc}'
        if exc.__cause__:
            msg += f". {exc.__cause__}"
        return (msg, 400)
    for matcher in Matcher.iter_all():
        if matcher.match(update):
            mission = Mission.find_one(uuid=matcher.mission_uuid)
            mission.last_update = update.in_game_time
            mission.save()
            return redirect(f"/mission/{matcher.mission_uuid}") # break loop

    # didn't match any missions, let the client know
    return ('', 202)
