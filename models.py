import dataset
from sqlalchemy.orm import DeclarativeBase
from flask import current_app, g

from datetime import datetime
from enum import Enum
from itertools import chain
from re import fullmatch
from uuid import uuid4


def get_db(reset=False):
    if reset or 'db' not in g:
        g.db = dataset.connect('sqlite:///:memory:')
    return g.db

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
        if time is None:
            raise ValueError
        self.time = time

    def as_datetime(self, separator=' '):
        timeparts = KTimeParts(self.time)
        timeparts.year += 1 # year starts at 1
        timeparts.day += 1 # same for day
        return f'Y{timeparts.year}D{timeparts.day:03}{separator}{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'

    def __sub__(self, other):
        return KTimestamp(self.time - other.time)

    def __eq__(self, other):
        return self.time == other.time

    def __lt__(self, other):
        return self.time < other.time

    def as_interval(self, separator=' '):
        timeparts = KTimeParts(self.time)
        if timeparts.year > 0:
            return f'{timeparts.year}Y{separator}{timeparts.day}D{separator}{timeparts.hour:01}H'
        if timeparts.day > 0:
            return f'{timeparts.day}D{separator}{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'
        return f'{timeparts.hour:01}:{timeparts.minute:02}:{timeparts.second:02}'

class FilterDict:
    _FIELDS = {}

    def __init__(self, obj):
        self._obj = obj

    @staticmethod
    def __idfn(x):
        return x

    def __getitem__(self, key):
        return self._FIELDS.get(key, self.__idfn)(self._obj[key])

    def __setitem__(self, key, val):
        self._obj[key] = val

    def __iter__(self):
        return iter(self._obj)

    def keys(self):
        return self._obj.keys()

    def values(self):
        raise NotImplementedError
        # return {k: self._FIELDS.get(k, self.__idfn) for k, v in self._obj.items()}

    def __len__(self):
        return len(self._obj)

    def copy(self):
        return self.__class__(self._obj.copy())

    def setdefault(self, key, val):
        return self._obj.setdefault(key, val)

    def update(self, other):
        return self._obj.update(other)

    def items(self):
        for key, val in self._obj.items():
            yield (key, self._FIELDS.get(key, self.__idfn)(val))

    def __delitem__(self, key):
        del self._obj[key]


class Model(FilterDict):

    def __init__(self, obj):
        '''
        ensure ID creation
        '''
        super().__init__(obj)
        if 'uuid' not in self._obj:
            self._obj['uuid'] = str(uuid4())

    @classmethod
    def iter_all(cls, **kwargs):
        db = get_db()
        return (cls(i) for i in db[cls.TABLENAME].all(**kwargs))

    @classmethod
    def find_one(cls, **kwargs):
        db = get_db()
        return cls(db[cls.TABLENAME].find_one(**kwargs))

    def save(self):
        db = get_db()
        db[self.TABLENAME].upsert(self._obj, ["uuid"])

    @staticmethod
    def _serializable(val):
        if isinstance(val, KTimestamp):
            return val.as_datetime()
        return val

    def as_dict(self):
        '''
        turn into a dict with all contents serializable for JSON
        '''
        val = {k: self._serializable(v) for k, v in self.items()}
        val['type'] = self._get_type_name()
        val['url'] = f'/{self._get_type_name()}/{self["uuid"]}'
        return val

class Mission(Model):
    TABLENAME = 'mission'

    @staticmethod
    def _timestamp_or_none(val):
        if val is None:
            return None
        return KTimestamp(val)


    _FIELDS = {
        'start': _timestamp_or_none,
        'last_update': _timestamp_or_none,
    }

    @classmethod
    def by_last_update(cls):
        return cls.iter_all(order_by='-last_update')

    def as_dict(self):
        d = super().as_dict()
        if all(self._obj.get(x) for x in ['last_update', 'start']):
            d['mission_elapsed_time'] = (self['last_update'] - self['start']).as_interval()
        else:
            d['mission_elapsed_time'] = None
        return d

    def _get_type_name(self):
        return 'mission'

class Matcher(Model):
    TABLENAME = 'matcher'
    # has: mission_id, vessel_name, soi_name

    def match(self, update):
        is_match = True # require all present filters to match
        if self._obj.get('vessel'):
            is_match = is_match and bool(fullmatch(self["vessel"], update.vessel_name))
        if self._obj.get("soi_name"):
            is_match = is_match and (update.soi_name == self["soi_name"])
        return is_match

    def _get_type_name(self):
        return 'matcher'

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

def GameStatus_or_none(val):
    return val and GameStatus(val) or None

def string_or_none(val):
    return val and str(val) or None

def float_or_none(val):
    return val and float(val) or None

class Update:
    '''
    Ephemeral data sent from the game with latest info on the scene.
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

