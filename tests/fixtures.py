from kspoverlay import app
from pytest import fixture

from tempfile import NamedTemporaryFile

from models import get_db

@fixture(name="app_ctx", scope='session')
def get_app_and_fresh_db():
    with app.app_context() as the_app, \
            NamedTemporaryFile() as temp_request_log, \
            NamedTemporaryFile() as temp_app_log, \
            NamedTemporaryFile() as temp_db:
        # recreate database in a one-per-session file
        get_db(url=temp_db.name, reset=True)
        
        # point to new, temporary files
        app.config['db_file'] = temp_db.name
        app.config['request_log'] = temp_request_log.name
        app.config['app_log'] = temp_app_log.name
    
        yield the_app
