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
from sys import stderr
from uuid import uuid4

# priorities can be any int
DEFAULT_PRIORITY = 5
# mean altitude of Rhode above TSB in meters
RHODE_MEAN_ALT = 13338.2 * 1000 * 1000
HOMEWORLDS = ['Kerbin', 'Rhode', 'Lua']
STARS = ['Kerbol', 'The Sun', 'Sun', 'Tempus System Barycenter']

def get_db(url=None, reset=False):
    '''
    return a Dataset instance.

    tries to cache the instance into the Flask app.
    '''
    if not url:
        url = current_app.config['db_file']

    if reset or 'db' not in g:
        g.db = dataset.connect(f'sqlite:///{url}')
        g.sessionmaker = sessionmaker(bind=g.db.engine)

    return g.db

def close_db():
    if 'session' in g:
        g.session.close()

    if 'db' in g:
        g.db.close()
        del g.db


# shared type conversions

def KTimeStamp_or_none(val):
    return val and KTimestamp(val) or None

def GameStatus_or_none(val):
    return val and GameStatus(val) or None

def int_or_none(val):
    return val and int(val) or None

def string_or_none(val):
    return val and str(val) or None

def float_or_none(val):
    return val and float(val) or None

# custom errors

class ValidationError(Exception):
    def __init__(self, message):
        self.message = message

# uuid conventions

def short_uuid(uuid):
    if not uuid:
        return '?'
    return uuid[:6] + '..' + uuid[-6:]


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
            time = self.parse(time)
        elif not isinstance(time, (float, int)):
            raise ValueError(f'unexpected type: {type(time)}')
        self.time = float(time)

    def as_datetime(self, separator=' '):
        timeparts = KTimeParts(self.time)
        timeparts.year += 1 # year starts at 1
        timeparts.day += 1 # same for day
        return f'Y{timeparts.year:n}D{timeparts.day:03n}{separator}{timeparts.hour:01n}:{timeparts.minute:02n}:{timeparts.second:02.0f}'

    @classmethod
    def parse(cls, datestring):
        '''
        'Y1D100 HH:MM:SS' -> int
        '''
        if datestring.isdigit():
            return cls(int(datestring))
        match = fullmatch(
            r'[yY](?P<year>\d+)[dD](?P<day>\d+)\s+(?P<hour>\d):(?P<minute>\d?\d):?(?P<second>\d?\d)?(?P<milisec>\.\d+)?',
            datestring)
        if not match:
            raise ValueError(f'unable to parse: {datestring}')
        # year and day start counting at 1
        yearnum = int(match.group('year')) - 1
        daynum = int(match.group('day')) - 1
        return (
            (yearnum * KTimeParts.SECS_PER_YEAR) +
            (daynum * KTimeParts.SECS_PER_DAY) + 
            (int(match.group('hour')) * KTimeParts.SECS_PER_HOUR) + 
            (int(match.group('minute')) * 60) + 
            (int(match.group('second'))) + 
            (float(match.group('milisec') or 0))
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

    def __repr__(self):
        retval = super().__repr__()
        return retval[:-1] + ' (' + short_uuid(self.uuid) + ')>'

    @classmethod
    def iter_all(cls, **kwargs):
        db = get_db()
        return (cls(i) for i in db[cls.TABLENAME].all(**kwargs))

    @classmethod
    def find_one(cls, _none_if_missing=False, **kwargs):
        db = get_db()
        found = db[cls.TABLENAME].find_one(**kwargs)
        if not found:
            if _none_if_missing:
                return None
            raise ValueError(f'no matching record: {kwargs}')
        return cls(found)

    @classmethod
    def delete_all(cls):
        db = get_db()
        db[cls.TABLENAME].delete()

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
        turn into a dict with all contents serializable for JSON.

        Uses as_db_row, which isn't great when transforms are run
        during the init, e.g. splitting a list stored as a string.
        '''
        val = self.as_db_row()
        val['type'] = self.JSON_TYPE_NAME
        val['url'] = f'/{self.JSON_TYPE_NAME}/{self.uuid}'
        return val

# data model notes
# Mission 1:* Vessel
# Vessel 1:* VesselProgress
# Vessel contains state machine for individual vessels
# but the overall "progress" as shown on screen is owned by Mission
# VesselProgress is a log, many entries for each Vessel
# Vessels get associated with a Mission via Matchers
# once associated, that association isn't updated
# this is usually ok - most vehicles are part of only one mission, 
# and then that mission gets archived
# archived missions aren't relevant to matching

# 'display' is the view that the frontend should show
# it is determined by:
# - a vessel gets matched to a mission


class Mission(Model):
    TABLENAME = 'mission'
    JSON_TYPE_NAME = 'mission'

    def __init__(self, row_obj):
        super().__init__(row_obj)
        self._start = KTimestamp(row_obj['start'])
        self.name = row_obj['name']
        self.steps = row_obj.get('steps', [])
        if self.steps == '':
            self.steps = []
        if isinstance(self.steps, str):
            self.steps = self.steps.split(';')
        self.cur_step = int_or_none(row_obj.get('cur_step', 0))
        self.archived = row_obj.get('archived', False)

    def __repr__(self):
        retval = super().__repr__()
        return retval[:-1] + ' (' + self.name + ')>'

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
            'steps': ';'.join(self.steps),
            'cur_step': self.cur_step,
            'archived': bool(self.archived),
        })
        return db_row

    def as_json_dict(self):
        vals = super().as_json_dict()
        vals['steps'] = self.steps
        return vals

    @classmethod
    def by_start(cls):
        return cls.iter_all(order_by='start')

class MatchFunction:
    '''
    returned by Matcher.match_functions

    Callable, returns True if provided Update matches.
    '''
    def __init__(self, mission_uuid, priority, params):
        self.mission_uuid = mission_uuid
        self.priority = priority
        self.params = params

    def __call__(self, update):
        is_match = True # require all present filters to match
        vessel_name = self.params.get('vessel_name')
        if vessel_name:
            is_match = is_match and bool(fullmatch(vessel_name, update.vessel_name))
        soi_name = self.params.get('soi_name')
        if soi_name:
            is_match = is_match and (update.soi_name == soi_name)
        return is_match

class Matcher(Model):
    TABLENAME = 'matcher'
    JSON_TYPE_NAME = 'matcher'
    # has: mission_uuid, vessel_name, soi_name

    def __init__(self, row_obj):
        super().__init__(row_obj)
        self.mission_uuid = row_obj['mission_uuid']
        self.vessel_name = row_obj.get('vessel_name')
        self.soi_name = row_obj.get('soi_name')
        self.priority = row_obj.get('priority') or DEFAULT_PRIORITY

        if not any([self.vessel_name, self.soi_name]):
            raise ValueError('must provide one of vessel_name, soi_name')

    def __repr__(self):
        retval = super().__repr__()
        return retval[:-1] + ' (vessel_name=' + repr(self.vessel_name) + \
            ', soi_name=' + repr(self.soi_name) + ')>'


    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'mission_uuid': self.mission_uuid,
            'vessel_name': self.vessel_name,
            'soi_name': self.soi_name,
            'priority': self.priority,
        })
        return db_row

    @classmethod
    def match_functions(cls):
        '''
        yield MatchFunctions for each valid Matcher
        Matchers go invalid once their associated Mission is archived,
        or if their Mission is missing (orphaned).
        '''
        db = get_db()
        for row in db.query('''
                SELECT 
                    matcher.mission_uuid,
                    matcher.vessel_name,
                    matcher.soi_name,
                    matcher.priority
                FROM
                    matcher INNER JOIN mission
                    ON matcher.mission_uuid = mission.uuid
                WHERE
                    mission.archived = 0
                ORDER BY
                    matcher.priority ASC'''):
            yield MatchFunction(
                row['mission_uuid'],
                row['priority'],
                {
                    'vessel_name': row['vessel_name'],
                    'soi_name': row['soi_name'],
                },
            )

    @classmethod
    def iter_all(cls, **kwargs):
        if 'order_by' not in kwargs:
            kwargs['order_by'] = 'priority'
        return super().iter_all(**kwargs)

class MissionTransitionListener:
    def after_transition(self, event, source, target):
        logger.warning(f"mission transition {source.id} -> {target.id}")
        raise Exception("below isn't being called; g isn't populated")
        if getattr(g, 'mission_uuid'):
            VesselProgress.record(g.mission_uuid, g.in_game_time, target.id)


class VesselProgress(Model):
    '''
    Log of mission state machine transitions for individual Vessels.

    in_game_time is the earliest that the vessel reached that milestone
    this allows for rollbacks checking IGT.
    '''
    TABLENAME = 'vessel_progress'
    
    def __init__(self, row_obj):
        super().__init__(row_obj)
        self.vessel_id = row_obj['vessel_id']
        self.in_game_time = row_obj['in_game_time']
        self.progress = row_obj['progress']

    def as_db_row(self):
        db_row = super().as_db_row()
        db_row.update({
            'vessel_id': self.vessel_id,
            'in_game_time': self.in_game_time,
            'progress': self.progress,
        })
        return db_row

    @classmethod
    def record(cls, vessel_id, in_game_time, progress):
        '''
        associate mission and progress at igt. all args are required.

        try to avoid duplicate records. Note we're not using transactions.
        '''
        if any(not i for i in [vessel_id, in_game_time, progress]):
            raise ValueError(f'invalid args: {vessel_id}, {in_game_time}, {progress}')

        if cls.find_one(
                vessel_id=vessel_id,
                progress=progress,
                _none_if_missing=True):
            # duplicate, ignore
            # even if the IGT increases
            return

        VesselProgress({
            'vessel_id': vessel_id,
            'progress': progress,
            'in_game_time': in_game_time,
        }).save()

class VesselMachine(StateChart):
    '''
    state machine for Vessel progress
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

    # listeners
    listeners = [MissionTransitionListener]
    
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
    TABLENAME = 'update'
    JSON_TYPE_NAME = 'update'

    def __init__(self, row_obj):
        '''
        apply type coercion according to ATTRS while copying from row_obj
        '''
        super().__init__(row_obj)
        self.irl_time = row_obj['irl_time']
        self.game_status = GameStatus_or_none(row_obj.get('game_status'))
        self.in_game_time = row_obj.get('in_game_time')
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
        # if isinstance(val, (float, int)):
            # TODO: remove this? shouldn't happen
            # raise ValueError('use datetimes instead')
        if isinstance(val, str):
            self._irl_time = datetime.fromisoformat(val).astimezone()
            return
        
        if not isinstance(val, datetime):
            raise ValueError(f'expected datetime, got: {type(val)}')
        self._irl_time = val.astimezone()

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
        self._in_game_time = KTimestamp.parse(val)

        # self._in_game_time = datetime.fromisoformat(val)
    
    @classmethod
    def get_latest(cls):
        try:
            return cls.find_one(order_by='-irl_time')
        except ValueError:
            return None

    @classmethod
    def put_latest(cls, vals):
        update = Update(vals)
        
        try:
            vessel = Vessel.find_one(uuid=update.vessel_id)
        except ValueError:
            # TODO: why doesn't this message run?
            logger.warning('previously-unseen vessel', vessel_id=update.vessel_id)
            vessel = Vessel({
                'uuid': update.vessel_id,
                'igt_last_update': update.in_game_time,
                'state': VesselMachine(),
            })

        if not vessel.mission_uuid:
            # vessel hasn't been associated with a mission, do matcher searchh
            for matcher in Matcher.match_functions():
                if matcher(update):
                    try:
                        mission = Mission.find_one(uuid=matcher.mission_uuid)
                    except ValueError as root_exc:
                        # explain this ValueError to be helpful
                        raise ValueError(f'mission {matcher.mission_uuid} referenced by matcher {matcher.uuid} does not exist') from root_exc
                    vessel.mission_uuid = mission.uuid
                    logger.warning(
                        'associating vessel with mission', 
                        vessel_id=update.vessel_id, 
                        mission_uuid=vessel.mission_uuid)
                    break
        
        # TODO handle IGT reversions
        # if IGT goes backwards, restore recorded state

        with logger.contextualize(
                mission_uuid=vessel.mission_uuid, vessel_id=update.vessel_id):
            # give state machine callbacks access to some important vars
            g.mission_uuid = vessel.mission_uuid
            g.in_game_time = update.in_game_time # TODO remove this, it's part of the update
            vessel.state.advance(update=update)
        update.save()

        vessel.igt_last_update = update.in_game_time
        vessel.save()
        return bool(vessel.mission_uuid)


class Vessel(Model):
    '''
    track progress per Vessel, which is KSP's identifier for a single vehicle

    Each mission has multiple Vessels
    '''
    TABLENAME = 'vessel'
    JSON_TYPE_NAME = 'vessel'

    def __init__(self, rowobj):
        # ksp's vessel ID
        self.uuid = rowobj['uuid']
        # when we last changed progress to a new value
        self.igt_last_update = rowobj['igt_last_update']
        # instantiate the state machine with last known state
        if isinstance(rowobj.get('state'), VesselMachine):
            self.state = rowobj['state']
        elif rowobj.get('state'):
            # convert string ID to initialized mm
            self.state = VesselMachine()
            self.state.current_state_value = rowobj['state']
        else:
            self.state = VesselMachine()
        # optional: mission id
        self.mission_uuid = rowobj.get('mission_uuid')

    def as_db_row(self):
        return {
            'uuid': self.uuid,
            'igt_last_update': self.igt_last_update,
            'state': self.state.configuration_values[0], # TODO This returns 'prelaunch'; does not update with latest state change
            'mission_uuid': self.mission_uuid,
        }
