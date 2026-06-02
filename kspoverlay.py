from flask import Flask, render_template, redirect, request

app = Flask(__name__)

class KTimeParts:
    HOURS_PER_DAY = 6
    DAYS_PER_YEAR = 426
    SECS_PER_DAY = 60*60*HOURS_PER_DAY
    SECS_PER_YEAR = 60*60*HOURS_PER_DAY*DAYS_PER_YEAR

    def __init__(self, timestamp):
        self.year = (timestamp // self.SECS_PER_YEAR)
        leftover = timestamp % self.SECS_PER_YEAR

        self.day = leftover // self.SECS_PER_DAY
        leftover = leftover % self.SECS_PER_DAY

        self.hour = leftover // (60 * 60)
        leftover = leftover % (60 * 60)

        self.minute = leftover // 60

        self.second = leftover % 60

class KTimestamp:
    def __init__(self, time):
        self.time = time

    def as_datetime(self, separator=' '):
        timeparts = KTimeParts(self.time)
        timeparts.year += 1 # year starts at 1
        timeparts.day += 1 # same for day
        return f'Y{timeparts.year}D{timeparts.day:03}{separator}{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'

    def __sub(self, other):
        return KTimestamp(self.time - other.time)

    def as_interval(self, separator=' '):
        timeparts = KTimeParts(self.time)
        if timeparts.year > 0:
            return f'{timeparts.year}Y{separator}{timeparts.day}D{separator}{timeparts.hour:01}H'
        if timeparts.day > 0:
            return f'{timeparts.day}D{separator}{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'
        return f'{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'

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
