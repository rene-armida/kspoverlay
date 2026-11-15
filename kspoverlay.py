from datetime import datetime
from enum import StrEnum
import json
import os
from tempfile import mktemp
from traceback import print_exc
from uuid import uuid4

from flask import Flask, flash, g, render_template, redirect, request, Response
from loguru import logger
import tomllib
import werkzeug.exceptions

from models import *

class Display(StrEnum):
    STANDBY = 'standby'
    FLIGHT = 'flight'
    PRELAUNCH = 'prelaunch'
    LAUNCH = 'launch'

app = Flask(__name__)

def _apply_conf(flask_app):
    '''
    load config from file, provide defaults where necessary

    require an environment var in order to differentiate from runs under test;
    otherwise db caching causes db url confusion and we end up modifying the 
    persistent db unintentionally.

    TODO this isn't perfect: the app assumes it's running under test
    unless redirected by environment variable. Better to have the test infra
    divert away, and let missing config errors propagate.
    '''
    # load config, let exceptions propagate
    # this doesn't work:
    # app.config.from_file("config.toml", load=tomllib.load, text=False)

    conf_path = os.environ.get('KSPOVERLAY_CONF')
    if not conf_path:
        conf = {
            'db_file': ':memory:',
            'request_log': ':temp:',
            'app_log': ':temp:',
            'SECRET_KEY': str(uuid4()),
        }
    else:
        with open(conf_path, 'rb') as config_fp:
            conf = tomllib.load(config_fp)
    flask_app.config.update(conf)
_apply_conf(app)

# log functions
def _log_functor(config_key):
    def get_log():
        '''
        return path to requested log file
        '''
        if app.config[config_key] == ':temp:':
            # TODO cleanup these log files on shutdown
            app.config[config_key] = mktemp(prefix=config_key, suffix='.log')
        return app.config[config_key]
    return get_log

get_request_log = _log_functor('request_log')
get_app_log = _log_functor('app_log')

# custom application logging
def short_uuid(uuid):
    if not uuid:
        return '?'
    return uuid[:6] + '..' + uuid[-6:]

def format_log(record):
    '''
    return format string for loguru record object
    '''
    fmt = "{time} | {level} | {module}:{function}:{line} - {message}"
    extra = record.get('extra', {})
    if extra.get('vessel_id'):
        extra['vessel_id_short'] = short_uuid(extra['vessel_id'])
        fmt += ' - vsl {vessel_id_short}' 
    if extra.get('mission_uuid'):
        extra['mission_uuid_short'] = short_uuid(extra['mission_uuid'])
        fmt += ' - msn {mission_uuid_short}'
    return fmt

logger.add(get_app_log(), format=format_log)

# avoid db concurrency errors
# see https://www.iditect.com/faq/python/using-sqlalchemy-session-from-flask-raises-quotsqlite-objects-created-in-a-thread-can-only-be-used-in-that-same-threadquot.html


@app.before_request
def before_request():
    # run the db connection just to get the app to create a sessionmaker
    get_db()
    g.session = g.sessionmaker()

@app.after_request
def after_request(response):
    if 'session' in g:
        g.session.close()

    close_db()
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

@app.route("/vessel/<vessel_id>", methods=["GET"])
def vessel_get(vessel_id):
    vessel = Vessel.find_one(uuid=vessel_id)
    if not vessel:
        return ('', 404)
    return vessel.as_json_dict()

@app.route("/vessel/<vessel_id>", methods=["PUT"])
def vessel_put(vessel_id):
    vessel = vessel.find_one(uuid=vessel_id)
    if not vessel:
        return ('', 404)
    for fn in ['igt_last_update', 'state', 'mission_uuid']:
        if fn in request.json:
            setattr(vessel, fn, request.json[fn])
    vessel.save()
    return ('', 200)

@app.route("/vessel/<matcher_uuid>", methods=["DELETE"])
def vessel_delete(vessel_id):
    vessel = Vessel.find_one(uuid=vessel_id)
    vessel.delete()
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
    '''
    plugin is sending us latest game data
    '''
    # log all requests, capture error output if an exception occurs
    with open(get_request_log(), 'a') as log_fp:
        # start of line
        log_fp.write('[' + datetime.now().strftime('%c') + '] ')
    with open(get_request_log(), 'ab') as log_fp:
        # request content is binary, dump as-is
        log_fp.write(request.get_data())
    with open(get_request_log(), 'a') as log_fp:
        log_fp.write('\n')
        try:
            request_json = request.get_json()
        except werkzeug.exceptions.BadRequest as exc:
            logger.error('Client sent invalid content, ignoring')
            return ('Invalid JSON content', 415)

        try:
            update = Update(request_json)
        except Exception as exc:
            log_fp.write('ERROR processing last request: ')
            print_exc(file=log_fp)

            msg = f'Invalid update data. {exc}'
            if exc.__cause__:
                msg += f". {exc.__cause__}"
            return (msg, 400)

    # find mission
    mission_uuid = None
    for matcher in Matcher.match_functions():
        if matcher(update):
            try:
                mission = Mission.find_one(uuid=matcher.mission_uuid)
            except ValueError:
                # broken reference
                return (f'Missing referenced mission id: {matcher.mission_uuid}', 500)
            mission_uuid = mission.uuid
            break


    try:
        vessel = Vessel.find_one(uuid=update.vessel_id)
    except ValueError:
        # TODO: why doesn't this message run?
        logger.warning('previously-unseen vessel', vessel_id=update.vessel_id, mission_id=mission_uuid)
        vessel = Vessel({
            'mission_uuid': mission_uuid,
            'uuid': update.vessel_id,
            'igt_last_update': update.in_game_time,
            'state': VesselMachine(),
        })

    with logger.contextualize(
            mission_uuid=mission_uuid, vessel_id=update.vessel_id):
        # give state machine callbacks access to some important vars
        g.mission_uuid = mission_uuid
        g.in_game_time = update.in_game_time
        vessel.state.advance(update=update)
    update.save()
    vessel.save()

    if mission_uuid:
        return ('', 200)

    # didn't match any missions, let the client know
    return ('', 202)

@app.route("/_display")
def get_display_latest():
    return Response(Display.STANDBY, content_type="text/plain")

@app.route("/update/_latest")
def get_update_latest():
    '''
    Vue app in OBS overlay is asking for latest info
    '''
    # get latest Update and associated Vessel + Mission
    update = Update.get_latest()
    if not update:
        return {
            'display': Display.STANDBY,
            'irlTime': datetime.now().strftime('%c'),
        }

    try:
        vessel = Vessel.find_one(uuid=update.vessel_id)
    except ValueError:
        vessel = None
    
    # TODO: capture mission_uuid in Update
    #try:
     #   mission = Mission.find_one(mission_uuid=update.mission_uuid)
    # except ValueError:
    #     mission = None
    
    # TODO when the display value changes, we need to send an HTTP
    # request to the OBS plugin. It'd be better to have the plugin
    # poll us, since it knows its own state (we have to record it otherwise)

    return {
        "display": vessel.progress.to_display(),
        "missionName": "hello", # mission.name
        'irlTime': datetime.now().strftime('%c'),
        'gameStatus': None, # TODO: this is for pause state, retain?
        'inGameTime': update.in_game_time.as_datetime(),
        'missionElapsedTime': (update.in_game_time - mission.in_game_time).as_interval() if mission else None
    }