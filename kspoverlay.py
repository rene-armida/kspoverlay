from flask import Flask, render_template, redirect, request
from models import *

app = Flask(__name__)

@app.template_filter()
def ktime(tval):
    return 


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
    return {
        'matcher': [
            matcher.as_dict() for matcher in Matcher.iter_all()
        ],
    }

@app.route("/mission")
def mission_list():
    return {
        'mission': [
            mission.as_dict() for mission in Mission.iter_all()
        ], 
    }
    
@app.route("/mission", methods=["POST"])
def mission_post():
    m = Mission.from_dict(request.json)
    m.save()
    return redirect(f'/mission/{m.id}')    

@app.route("/mission/<int:id>", methods=["PUT"])
def mission_put():
    Mission.from_dict(request.json()).save()



