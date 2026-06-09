import tomllib

from flask import Flask, render_template, redirect, request
from models import *

app = Flask(__name__)
# load config, let exceptions propagate
app.config.from_file("config.toml", load=tomllib.load, text=False)

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
    return render_template('index.html')

@app.route("/standby")
def standby():
    return render_template('standby.html')

@app.route("/flight")
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
    return [matcher.as_dict() for matcher in Matcher.iter_all()]

@app.route("/mission")
def mission_list():
    return [mission.as_dict() for mission in Mission.iter_all()]

@app.route("/mission", methods=["POST"])
def mission_post():
    Mission(request.json).save()
    m = Mission.find_one(name=request.json['name'])
    return redirect(f'/mission/{m["id"]}')

@app.route("/mission/<mission_uuid>", methods=["GET"])
def mission_get(mission_uuid):
    mission = Mission.find_one(uuid=mission_uuid)
    if not mission:
        return '', 404
    mission = mission.as_dict()
    #mission['url'] = f"/mission/{mission['uuid']}"
    return mission

@app.route("/mission/<mission_uuid>", methods=["PUT"])
def mission_put(mission_uuid):
    Mission.from_dict(request.json()).save()

@app.route("/update", methods=["POST"])
def update_post():
    update = Update(**request.json)
    for matcher in Matcher.iter_all():
        if matcher.match(update):
            mission = Mission.find_one(uuid=matcher["mission_uuid"])
            mission["last_update"] = update.in_game_time
            mission.save()
            return redirect(f"/mission/{matcher['mission_uuid']}") # break loop

    # didn't match any missions, let the client know
    return ('', 202)
