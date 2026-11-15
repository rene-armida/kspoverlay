from kspoverlay import app
from pytest import fixture

from tempfile import NamedTemporaryFile

from models import get_db

@fixture(name="app_ctx", scope='session')
def get_app_and_fresh_db():
    with app.app_context() as the_app, \
            NamedTemporaryFile() as temp_request_log, \
            NamedTemporaryFile() as temp_app_log:
        # recreate database in memory
        get_db(url=":memory:", reset=True)
        
        # point logs to new, temporary files
        app.config['request_log'] = temp_request_log.name
        app.config['app_log'] = temp_app_log.name
    
        yield the_app
