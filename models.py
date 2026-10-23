import dataset
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlite3 import PrepareProtocol

from flask import current_app, g

from datetime import datetime
from enum import StrEnum, Enum
from itertools import chain
from re import fullmatch
from uuid import uuid4


def get_db(url=None, reset=False):
    if not url:
        url = current_app.config['db_file']

    if reset or 'db' not in g:
        g.db = dataset.connect(f'sqlite:///{url}')
        g.sessionmaker = sessionmaker(bind=g.db.engine)
    return g.db

# shared type conversions

def KTimeStamp_or_none(val):
    return val and KTimestamp(val) or None

def GameStatus_or_none(val):
    return val and GameStatus(val) or None

def string_or_none(val):
    return val and str(val) or None

def float_or_none(val):
    return val and float(val) or None

# custom errors

class ValidationError(Exception):
    def __init__(self, message):
        self.message = message

# types

class KTimeParts:
    HOURS_PER_DAY = 6
    DAYS_PER_YEAR = 426
    SECS_PER_DAY = 60*60*HOURS_PER_DAY
    SECS_PER_YEAR = 60*60*HOURS_PER_DAY*DAYS_PER_YEAR
    SECS_PER_HOUR = 60*60

    def __init__(self, timestamp):
        '''
        break out timestamp (float) into attrs for year, day, etc.
        '''
        self.year = (timestamp // self.SECS_PER_YEAR)
        leftover = timestamp % self.SECS_PER_YEAR

        self.day = leftover // self.SECS_PER_DAY
        leftover = leftover % self.SECS_PER_DAY

        self.hour = leftover // (self.SECS_PER_HOUR)
        leftover = leftover % (self.SECS_PER_HOUR)

        self.minute = leftover // 60

        self.second = leftover % 60

class KTimestamp:
    def __init__(self, time):
        '''
        time is either an int or float (time since epoch at game start),
        or a string 'YxDy HH:MM:SS'

        self.time is always float after
        '''
        if time is None:
            raise ValueError('expected int or float, None provided')
        if isinstance(time, str):
            time = self.parse(time, strict=True)
        elif not isinstance(time, (float, int)):
            raise ValueError(f'unexpected type: {type(time)}')
        self.time = float(time)

    def as_datetime(self, separator=' '):
        timeparts = KTimeParts(self.time)
        timeparts.year += 1 # year starts at 1
        timeparts.day += 1 # same for day
        return f'Y{timeparts.year:n}D{timeparts.day:03n}{separator}{timeparts.hour:01n}:{timeparts.minute:02n}:{timeparts.second:02.0f}'

    @classmethod
    def parse(cls, datestring, strict=False):
        '''
        'Y1D100 HH:MM:SS' -> int
        '''
        if datestring.isdigit():
            return cls(int(datestring))
        match = fullmatch(
            r'[yY](?P<year>\d+)[dD](?P<day>\d+)\s+(?P<hour>\d):(?P<minute>\d?\d):?(?P<second>\d?\d)?',
            datestring)
        if not match:
            if strict:
                raise ValueError(f'unable to parse: {datestring}')
            return None
        # year and day start counting at 1
        yearnum = int(match.group('year')) - 1
        daynum = int(match.group('day')) - 1
        return (
            (yearnum * KTimeParts.SECS_PER_YEAR) +
            (daynum * KTimeParts.SECS_PER_DAY) + 
            (int(match.group('hour')) * KTimeParts.SECS_PER_HOUR) + 
            (int(match.group('minute')) * 60) + 
            (int(match.group('second')))
        )

    def timeparts(self):
        return KTimeParts(self.time)

    def __sub__(self, other):
        return KTimestamp(self.time - other.time)

    def __eq__(self, other):
        return self.time == other.time

    def __lt__(self, other):
        return self.time < other.time

    def as_interval(self, separator=' '):
        timeparts = KTimeParts(self.time)
        if timeparts.year > 0:
            # truncated format - don't show minutes and seconds
            return f'{timeparts.year:.0f}Y{separator}{timeparts.day:.0f}D{separator}{timeparts.hour:01.0f}H'

        fmt = r'{timeparts.hour:01.0f}:{timeparts.minute:02.0f}:{timeparts.second:02.0f}'
        if timeparts.day > 0:
            fmt = r'{timeparts.day:.0f}D{separator}' + fmt
        return fmt.format(**locals())

    def __conform__(self, protocol):
        '''
        make instances of this class adaptable to the database
        '''
        if protocol is PrepareProtocol:
            return self.time

class Model:
    # class attrs
    # TABLENAME: database table name
    # JSON_TYPE_NAME: how to describe this type over the wire

    def __init__(self, row_obj):
        '''
        copy values from a Datasets row, and ensure a UUID is created
        '''
        for k, v in row_obj.items():
            setattr(self, k, v)
        if not hasattr(self, 'uuid'):
            self.uuid = str(uuid4())

    @classmethod
    def iter_all(cls, **kwargs):
        db = get_db()
        return (cls(i) for i in db[cls.TABLENAME].all(**kwargs))

    @classmethod
    def find_one(cls, **kwargs):
        db = get_db()
        found = db[cls.TABLENAME].find_one(**kwargs)
        if not found:
            raise ValueError(f'no matching record: {kwargs}')
        return cls(found)

    def as_db_row(self):
        '''
        return a database row - a dict - for storage
        '''
        return {
            'uuid': self.uuid
        }

    def save(self):
        db = get_db()
        db[self.TABLENAME].upsert(self.as_db_row(), ["uuid"])

    def delete(self):
        db = get_db()
        db[self.TABLENAME].delete(uuid=self.uuid)

    def as_json_dict(self):
        '''
        turn into a dict with all contents serializable for JSON
        '''
        val = self.as_db_row()
        val['type'] = self.JSON_TYPE_NAME
        val['url'] = f'/{self.JSON_TYPE_NAME}/{self.uuid}'
        return val

class Mission(Model):
    TABLENAME = 'mission'
    JSON_TYPE_NAME = 'mission'

    def __init__(self, row_obj):
        super().__init__(row_obj)
        self._start = KTimestamp(row_obj['start'])
        self.name = row_obj['name']

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, val):
        self._start = KTimestamp(val)

    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'start': self._start.time, # stored as a number
            'name': self.name,
        })
        return db_row

    @classmethod
    def by_start(cls):
        return cls.iter_all(order_by='start')


class Matcher(Model):
    TABLENAME = 'matcher'
    JSON_TYPE_NAME = 'matcher'
    # has: mission_id, vessel_name, soi_name

    def __init__(self, row_obj):
        super().__init__(row_obj)
        self.mission_uuid = row_obj['mission_uuid']
        self.vessel_name = row_obj['vessel_name']
        self.soi_name = row_obj['soi_name']

    def match(self, update):
        is_match = True # require all present filters to match
        if self.vessel_name:
            is_match = is_match and bool(fullmatch(self.vessel_name, update.vessel_name))
        if self.soi_name:
            is_match = is_match and (update.soi_name == self.soi_name)
        return is_match

    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'mission_uuid': self.mission_uuid,
            'vessel_name': self.vessel_name,
            'soi_name': self.soi_name,
        })
        return db_row

    @classmethod
    def iter_all(cls, **kwargs):
        if 'order_by' not in kwargs:
            kwargs['order_by'] = 'priority'
        return super().iter_all(**kwargs)

class Progress(Enum):
    '''
    A vessel's progress forward in a mission; queried to determine
    which transitions and displays should be used

    This is based around the KSP "Situation" enum
    https://anatid.github.io/XML-Documentation-for-the-KSP-API/class_vessel.html#acea90b73d9b4523383503ec82f2f63bb

    But because we are re-ordering and dropping some of the constants,
    we change the name. Also, we won't ever go backwards in this scheme;
    vehicles only increase in Progress.
    '''
    # before the first stage is activated
    PRELAUNCH = 10
    # on ascent to orbit, including sub-orbital flight out of atmo
    LAUNCH = 20
    # orbital maneuvers around the homeworld and/or its satellites
    HOME_ORBIT = 30
    # outside homeworld soi
    TRANSFER_OUT = 40
    # mid-mission entry, descent, and landing
    # we don't have a good way of automatically detecting this,
    # but it'd eventually be nice to have new graphics here
    REMOTE_EDL = 50
    # touchdown achieved, operations on another body
    REMOTE_LANDED = 60
    # return to orbit around another body
    # another opportunity to add graphics later
    REMOTE_ASCENT = 70
    # back in orbit around another body
    # may include being docked at a station for a long time
    REMOTE_ORBIT = 80
    # returning to the homeworld
    TRANSFER_IN = 90
    # in homeworld SOI. May include docking at stations in SOI
    HOME_ORBIT_RETURN = 100
    # reentering atmo at the homeworld
    # usually in a small crew recovery pod
    HOME_EDL = 110
    # crew is returned to the surface
    HOME_LANDED = 120

class GameStatus(StrEnum):
    FLIGHT = 'flight'
    PAUSED_FLIGHT = 'paused-flight'
    SPACE_CENTER = 'space-center'
    VAB = 'vehicle-assembly'
    SPH = 'spaceplane-hangar'
    MISSION_CONTROL = 'mission-control'
    ADMINISTRATION = 'administration'
    TRACKING_STATION = 'tracking-station'
    ASTRONAUT_COMPLEX = 'astronaut-complex'
    RESEARCH_DEVELOPMENT = 'research-development'

class Update(Model):
    '''
    Ephemeral data sent from the game with latest info on the scene.

    Updates are sent from the plugin in the game on a periodic basis.
    This can quickly balloon in size and store large numbers of records,
    but only the most recent is important.
    '''
    TABLENAME = 'game_update'
    JSON_TYPE_NAME = 'update'
    CHART_FIELDS = [
        'in_game_time',
        'roll',
        'pitch',
        'heading',
        'velocity',
        'velocity_h',
        'velocity_v',
        'altitude_terrain',
        'altitude_sea_level',
        'dv_last_stage',
    ]

    def __init__(self, row_obj):
        '''
        apply type coercion according to ATTRS while copying from row_obj
        '''
        super().__init__(row_obj)
        self.irl_time = row_obj['irl_time']
        self.game_status = GameStatus_or_none(row_obj.get('game_status'))
        self._in_game_time = float_or_none(row_obj.get('in_game_time'))
        self.vessel_name = string_or_none(row_obj.get('vessel_name'))
        self.soi_name = string_or_none(row_obj.get('soi_name'))
        self.dv_last_stage = float_or_none(row_obj.get('dv_last_stage'))
        self.altitude_sea_level = float_or_none(row_obj.get('altitude_sea_level'))
        self.altitude_terrain = float_or_none(row_obj.get('altitude_terrain'))
        self.velocity = float_or_none(row_obj.get('velocity'))
        self.velocity_h = float_or_none(row_obj.get('velocity_h'))
        self.velocity_v = float_or_none(row_obj.get('velocity_v'))
        self.roll = float_or_none(row_obj.get('roll'))
        self.pitch = float_or_none(row_obj.get('pitch'))
        self.heading = float_or_none(row_obj.get('heading'))

    def __lt__(self, other):
        return self.irl_time < other.irl_time

    def save(self):
        '''
        override: only save the latest info; db singleton
        '''
        table = get_db()[self.TABLENAME]

        # delete all records
        table.delete()

        # insert this record. this assumes records always arrive in chrono order
        table.insert(self.as_db_row())


    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'irl_time': self._irl_time,
            'game_status': self.game_status,
            'in_game_time': self._in_game_time,
            'vessel_name': self.vessel_name,
            'soi_name': self.soi_name,
            'dv_last_stage': self.dv_last_stage,
            'altitude_sea_level': self.altitude_sea_level,
            'altitude_terrain': self.altitude_terrain,
            'velocity': self.velocity,
            'velocity_h': self.velocity_h,
            'velocity_v': self.velocity_v,
            'roll': self.roll,
            'pitch': self.pitch,
            'heading': self.heading,
        })
        return db_row

    @property
    def irl_time(self):
        return self._irl_time

    @irl_time.setter
    def irl_time(self, val):
        '''
        accept floats and ints directly, otherwise parse
        '''
        if isinstance(val, (float, int)):
            self._irl_time = val
        else:
            self._irl_time = datetime.fromisoformat(val)

    @property
    def in_game_time(self):
        return self._in_game_time

    @in_game_time.setter
    def in_game_time(self, val):
        '''
        accept (float, int, None) directly, otherwise parse
        '''
        if isinstance(val, (float, int)):
            self._in_game_time = val
            return

        if val is None:
            self._in_game_time = None
            return

        self._in_game_time = datetime.fromisoformat(val)
    
    @classmethod
    def get_latest(cls):
        try:
            return cls.find_one(order_by='-irl_time')
        except ValueError:
            return None

    def dump_chart_fields(self, dumpfp):
        dumpfp.write(
            ','.join(str(getattr(self, attrname)) for attrname in self.CHART_FIELDS))
        dumpfp.write('\n')

    def to_vessel(self):
        if update.situation == 'PRELAUNCH':
            progresses = [Progress.PRELAUNCH]
        elif update.situtaion in ['FLYING', 'SUBORBITAL'] and update.soi_name in ['Rhode', 'Lua']:
            progresses = [Progress.LAUNCH, Progress.HOME_EDL]
        elif update.situtaion == 'ORBITING' and update.soi_name in ['Rhode', 'Lua']:
            progress = [Progress.HOME_ORBIT, Progress.HOME_ORBIT_RETURN]
        elif update.situation in ['LANDED', 'SPLASHED'] and update.soi_name in ['Rhode', 'Lua']:
            progress = [Progress.HOME_LANDED]
        
        return [
            Vessel({
                'uuid': self.vessel_id,
                'igt_last_update': update.in_game_time,
                'progress': progress.value})
            for progress in progresses]

class Vessel(Model):
    def __init__(self, rowobj):
        '''
        This should only ever be called by record_progress
        '''
        # ksp's vessel ID
        self.uuid = rowobj['uuid']
        # when we last changed progress to a new value
        self.igt_last_update = rowobj['igt_last_update']
        # our own version of KSP's "Situation"
        self.progress = Progress(rowobj['progress'])

    def as_db_row(self):
        return {
            'uuid': self.uuid,
            'igt_last_update': self.igt_last_update,
            'progress': self._progress.value,
        }

    @classmethod
    def record_progress(cls, update):
        '''
        which display and transitions should be shown?
        '''
        vessel = Vessel.find_one(uuid=update.vessel_id)
        transition = '' # todo
        
        for new_vessel in update.to_vessel():
            if not vessel:
                # first time we're seeing this id, save it
                new_vessel.save()
                return
            if new_vessel.igt_last_update < vessel.igt_last_update:
                # time went backward, assume we are reverting
                new_vessel.save()
                return
            if new_vessel.progress.value > vessel.progress.value:
                # progress is increasing, we just transitioned
                new_vessel.save()

                return

        # we should not get here
        raise Exception('could not determine progress')
