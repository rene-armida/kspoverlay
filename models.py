import dataset
from loguru import logger
from statemachine import StateChart, State
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlite3 import PrepareProtocol

from flask import current_app, g

from datetime import datetime
from enum import StrEnum, Enum
from itertools import chain
from re import fullmatch
from uuid import uuid4


# mean altitude of Rhode above TSB in meters
RHODE_MEAN_ALT = 13338.2 * 1000 * 1000
HOMEWORLDS = ['Kerbin', 'Rhode', 'Lua']
STARS = ['Kerbol', 'The Sun', 'Sun', 'Tempus System Barycenter']

def get_db(url=None, reset=False):
    if not url:
        url = current_app.config['db_file']

    if reset or 'db' not in g:
        g.db = dataset.connect(f'sqlite:///{url}')
        g.sessionmaker = sessionmaker(bind=g.db.engine)
    return g.db

def close_db():
    if 'db' in g:
        g.db.close()
        del g.db

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
    # has: mission_uuid, vessel_name, soi_name

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

class MissionTransitionLogger:
    def after_transition(self, event, source, target):
        logger.warning(f"mission transition {source.id} -> {target.id}")

class MissionMachine(StateChart):
    '''
    state machine for transitions between Progress values
    '''
    # states
    prelaunch = State(initial=True)
    launch = State()
    home_orbit = State()
    transfer_out = State()
    remote_edl = State()
    remote_landed = State()
    remote_ascent = State()
    remote_orbit = State()
    transfer_in = State()
    home_orbit_return = State()
    home_edl = State()
    home_landed = State(final=True)

    # chart

    advance = (
        prelaunch.to(launch, cond="launch_start")
        | launch.to(home_orbit, cond="launch_end") 
        | home_orbit.to(transfer_out, cond="transfer_out_start") 
        | transfer_out.to(remote_edl, cond="direct_edl")
        | transfer_out.to(remote_orbit, cond="transfer_out_orbit")
        | remote_edl.to(remote_landed, cond="remote_edl_end")
        | remote_landed.to(remote_ascent, cond="remote_landed_end")
        | remote_ascent.to(remote_orbit, cond="launch_end")
        | remote_orbit.to(transfer_in, cond="remote_orbit_transfer_in")
        | remote_orbit.to(transfer_out, cond="remote_orbit_transfer_out")
        | transfer_in.to(home_orbit_return, cond="transfer_in_end")
        | home_orbit_return.to(home_edl, cond="remote_landed_end")
        | home_edl.to(home_landed, cond="remote_edl_end")
    )

    # TODO: revert guesses
    # when IGT goes backward, we are forced to guess the prior state
    # we can make some educated guesses
    # all of these will use the same cond function to check IGT

    # listeners
    listeners = [MissionTransitionLogger]
    
    def launch_start(self, update=None, **kwargs):
        return update.situation == 'FLYING'

    def launch_end(self, update=None, **kwargs):
        return update.situation == 'ORBITING'

    def transfer_out_start(self, update=None, **kwargs):
        return update.soi_name in STARS

    def direct_edl(self, update=None, **kwargs):
        return update.soi_name not in STARS and update.situation == 'SUBORBITAL'

    def transfer_out_orbit(self, update=None, **kwargs):
        return update.soi_name not in STARS and update.situation == 'ORBITING'

    def remote_edl_end(self, update=None, **kwargs):
        return update.situation in ['LANDED', 'SPLASHED']

    def remote_landed_end(self, update=None, **kwargs):
        return update.situation in ['FLYING', 'SUBORBITAL']

    def remote_orbit_transfer_out(self, update=None, **kwargs):
        '''
        leaving Merced, heading outbound to Kerbol or other destination beyond Rhode
        '''
        # engine should be firing, maneuver node exists and is on another soi
        return False
        # TODO
        return update.thrust > 0

    def remote_orbit_transfer_in(self, update=None, **kwargs):
        # TODO see above
        return False

    def transfer_in_end(self, update=None, **kwargs):
        return update.soi_name in HOMEWORLDS and update.situation == 'ORBITING'


class Display(StrEnum):
    '''
    what view is the front-end showing?
    '''
    NODATA = 'nodata' # startup, don't know what to show yet
    FLIGHT = 'flight' # generic flight, show chrono + mission
    FLIGHT_PAUSE = 'flightPause' # ESC menu active, hide it
    LAUNCH = 'launch' # small game + charts
    LAUNCH_PAUSE = 'launchPause' # ESC menu active during launch

class GameStatus(StrEnum):
    # TODO: still necessary?
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
        self.vessel_id = string_or_none(row_obj.get('vessel_id'))
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
        self.mission_uuid = string_or_none(row_obj.get('mission_uuid'))

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
            'vessel_id': self.vessel_id,
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
            'mission_uuid': self.mission_uuid,
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


class Vessel(Model):
    TABLENAME = 'vessel'

    def __init__(self, rowobj):
        # ksp's vessel ID
        self.uuid = rowobj['uuid']
        # when we last changed progress to a new value
        self.igt_last_update = rowobj['igt_last_update']
        # TODO Move this to Progress, separate state ID value and ephemeral machine into diff attrs
        # instantiate the state machine with last known state
        if isinstance(rowobj.get('state'), MissionMachine):
            self.state = rowobj['state']
        else:
            # convert string ID to initialized mm
            self.state = MissionMachine(
                getattr(MissionMachine, rowobj['state']))

    def as_db_row(self):
        return {
            'uuid': self.uuid,
            'igt_last_update': self.igt_last_update,
            'state': self.state.configuration_values[0],
        }
