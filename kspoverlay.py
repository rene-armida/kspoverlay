from flask import Flask, render_template, redirect, request

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/standby")
def standby():
    return render_template('standby.html')

@app.route("/flight")
def flight():
    args = {}
    if 'scale' in request.args:
        args['scale'] = request.args['scale']
    return render_template('flight.html', **args)
