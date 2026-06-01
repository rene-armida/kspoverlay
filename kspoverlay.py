from flask import Flask, render_template, redirect, request

app = Flask(__name__)

class KTimestamp:
    HOURS_PER_DAY = 6
    DAYS_PER_YEAR = 426
    SECS_PER_DAY = 60*60*HOURS_PER_DAY
    SECS_PER_YEAR = 60*60*HOURS_PER_DAY*DAYS_PER_YEAR

    def __init__(self, time):
        self.time = time

    def as_datetime(self, separator=''):
        year = self.time // self.SECS_PER_YEAR
        leftover = self.time % self.SECS_PER_YEAR
        day = leftover // self.SECS_PER_DAY

        leftover = leftover % self.SECS_PER_DAY
        hour = leftover // 60 * 60

        leftover = leftover % (60 * 60)
        minute = leftover // 60

        second = leftover % 60

        return f'Y{year}{separator}D{day:000} {hour:00}:{minute:00}:{second:00}'

    def as_interval(self, separator=''):
        return ''

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
