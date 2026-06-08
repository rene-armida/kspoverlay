import dataset
from sqlalchemy.orm import DeclarativeBase
from flask import current_app, g

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

class Update:
    '''
    Ephemeral data sent from the game with latest info on the scene.
    '''
    def __init__(self, vessel_name=None, soi_name=None, in_game_time=None):
        self.vessel_name = vessel_name
        self.soi_name = soi_name
        self.in_game_time = in_game_time

