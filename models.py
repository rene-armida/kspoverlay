import dataset
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlite3 import PrepareProtocol

from flask import current_app, g

from datetime import datetime
from enum import Enum
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
        return f'Y{timeparts.year:n}D{timeparts.day:03n}{separator}{timeparts.hour:01n}:{timeparts.minute:02n}:{timeparts.second:02n}'

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
        self._last_update = KTimestamp(row_obj['last_update'])
        self.name = row_obj['name']

    @property
    def mission_elapsed_time(self):
        return (
            all([self._last_update, self._start]) and
            (self._last_update - self._start).as_interval()
        )

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, val):
        self._start = KTimestamp(val)

    @property
    def last_update(self):
        return self._last_update

    @last_update.setter
    def last_update(self, val):
        self._last_update = KTimestamp(val)

    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'start': self._start.time, # stored as a number
            'last_update': self._last_update.time, # stored as a number
            'name': self.name,
        })
        return db_row

    @classmethod
    def by_start(cls):
        return cls.iter_all(order_by='start')

    @classmethod
    def by_last_update(cls):
        return cls.iter_all(order_by='-last_update')

    def as_json_dict(self):
        json_dict = super().as_json_dict()
        json_dict['mission_elapsed_time'] = self.mission_elapsed_time
        return json_dict

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

class GameStatus(Enum):
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

class Update:
    '''
    Ephemeral data sent from the game with latest info on the scene.

    Note - this isn't a Model! Data is copied from this into db-backed
    Model instances as necessary.
    '''
    # TODO unify with filterdict - maybe use it? idk
    ATTRS = {
        'irl_time': datetime.fromisoformat,
        'game_status': GameStatus_or_none,
        'in_game_time': float_or_none,
        'vessel_name': string_or_none,
        'soi_name': string_or_none,
        'dv_last_stage': float_or_none,
        'altitude_sea_level': float_or_none,
        'altitude_terrain': float_or_none,
        'velocity': float_or_none,
        'velocity_h': float_or_none,
        'velocity_v': float_or_none,
        'roll': float_or_none,
        'pitch': float_or_none,
        'heading': float_or_none,
    }

    def __init__(self, **kwargs):
        '''
        apply type coercion according to ATTRS while copying from kwargs
        '''
        for attrname, attrval in kwargs.items():
            try:
                typefunc = self.ATTRS.get(attrname, lambda x: x)
                setattr(self, attrname, typefunc(attrval))
            except Exception as exc:
                raise Exception(f"invalid data for field: {attrname}") from exc

    def __lt__(self, other):
        return self.irl_time < other.irl_time

    @classmethod
    def from_json(cls, jsondata):
        gdata = jsondata.get("data")
        return Update(
            irl_time=jsondata["date"],
            game_status=gdata["Status"],
            in_game_time=gdata.get("InGameTime"),
            soi_name=gdata.get("BodyName"),
            vessel_name=gdata.get("VesselName"),
            dv_last_stage=gdata.get("DVLastStage"),
        )

