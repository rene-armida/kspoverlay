import dataset
from sqlalchemy.orm import DeclarativeBase
from flask import current_app, g

from re import fullmatch
from uuid import uuid4


def get_db():
    if 'db' not in g:
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

class FilterDict:
    _FIELDS = {}

    def __init__(self, obj):
        self._obj = obj

    @staticmethod
    def __idfn(x):
        return x

    def __getitem__(self, key):
        if key in self._FIELDS:
            return self._FIELDS[key](self._obj[key])
        return self._obj[key]

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


class Model(FilterDict):
    @classmethod
    def iter_all(cls):
        db = get_db()
        return (cls(i) for i in db[cls.TABLENAME].all())

    @classmethod
    def find_one(cls, **kwargs):
        db = get_db()
        return cls(db[cls.TABLENAME].find_one(**kwargs))

    def save(self):
        db = get_db()
        if self._obj.get("id"):
            db[self.TABLENAME].update(self._obj, ["id"])
        else:
            db[self.TABLENAME].insert(self._obj)

class Mission(Model):
    TABLENAME = 'mission'
    _FIELDS = {
        'start': KTimestamp,
        'last_update': KTimestamp,
    }


class SOIMatcher(Model):
    TABLENAME = 'soi_matcher'
    # has: mission_id, soi name

    def match(self, update):
        return update.soi_name == self["soi_name"]


class VesselMatcher(Model):
    TABLENAME = 'vessel_matcher'
    # has: mission_id, vessel

    def match(self, update):
        return bool(fullmatch(self["vessel"], update.vessel_name))


class Update:
    '''
    Ephemeral data sent from the game with latest info on the scene.
    '''
    def __init__(self, vessel_name, soi_name):
        self.vessel_name = vessel_name
        self.soi_name = soi_name

