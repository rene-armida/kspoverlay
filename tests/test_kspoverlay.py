from models import KTimestamp, Mission, Matcher, get_db
from kspoverlay import app

from datetime import datetime
import re
from tempfile import NamedTemporaryFile

from pytest import fixture, mark

@fixture(name="app_ctx")
def get_app_and_fresh_db():
	with app.app_context() as the_app, \
			NamedTemporaryFile() as temp_request_log:
		# recreate database in memory
		get_db(url=":memory:", reset=True)

		# point request log to a new, temporary file
		app.config['request_log'] = temp_request_log.name
	
		yield the_app

@fixture(name="app_ctx_chart")
def get_chart_enabled_app(app_ctx):
	with NamedTemporaryFile() as temp_chart_log:
		app.config['chart_log'] = temp_chart_log.name
		yield app

def test_mission_list(app_ctx):
	client = app.test_client()
	resp = client.get('/mission')
	assert 200 == resp.status_code
	assert [] == resp.get_json()

	m1 = Mission({"name": "m1", "start": 1, "last_update": 1000})
	m1.save()
	m2 = Mission({"name": "m2", "start": 25, "last_update": 2000})
	m2.save()

	actual = client.get("/mission").json
	expected = [
		{
			"uuid": m1.uuid,
			"type": "mission",
			"name": "m1",
			"start": 1,
			"url": f"/mission/{m1.uuid}",
		},
		{
			"uuid": m2.uuid,
			"type": "mission",
			"name": "m2",
			"start": 25,
			"url": f"/mission/{m2.uuid}",
		}
	]
	assert expected == actual

def test_mission_get(app_ctx):
	client = app.test_client()
	Mission({"name": "m1", "start": 1}).save()
	Mission({"name": "m2", "start": 50}).save()
	m = Mission.find_one(name="m2")
	assert m.as_json_dict() == client.get(f"/mission/{m.uuid}").json

def test_post_update_not_json(app_ctx):
	client = app.test_client()
	resp = client.post("/update", "blah")
	assert 415 == resp.status_code # media type not supported, because it's plain text

	resp = client.post("/update", "blah", headers={"Content-Type": "application/json"})
	assert 415 == resp.status_code # bad request, because it doesn't deserialize

test_request_log_testdata = [
	# no 'irl_time'
	({"beep": '2026-07-03T21:25:56.778929+00:00'}, ['KeyError', 'irl_time']),
	# no 'Status'
	# ({"date": '2026-07-03T21:25:56.778929+00:00'}, ['TypeError', 'Status']),
	# irl_time is unrecognizeable
	({"irl_time": "abc"}, ['ValueError', 'irl_time']),
]

@mark.parametrize('request_data,expected_tokens', test_request_log_testdata)
def test_request_log(app_ctx, request_data, expected_tokens):
	client = app.test_client()
	resp = client.post('/update', json=request_data)

	assert 400 == resp.status_code
	with open(app.config['request_log']) as log_fp:
		content = log_fp.read()
		for expected_token in expected_tokens:
			assert expected_token in content, content


def test_post_update(app_ctx):
	m1 = Mission({"name": "m1", 'start': 100, 'last_update': 200})
	m1.save()
	m2 = Mission({"name": "m2", 'start': 150, 'last_update': 202})
	m2.save()
	Matcher({
		"vessel_name": "Freighter Alpha.*", 
		"mission_uuid": m1.uuid,
		"soi_name": None,
	}).save()
	Matcher({
		"vessel_name": None,
		"soi_name": "Gateway",
		"mission_uuid": m2.uuid,
	}).save()

	client = app.test_client()
	resp = client.post(
		"/update",
		json={
			"irl_time": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"in_game_time": 121.183,
			"soi_name": "Kerbin",
			"vessel_name": "Stayputnik",
		}
	)
	class AssertMsg:
		def __init__(self, resp_text):
			self.resp_text = resp_text

		def __repr__(self):
			'''
			called by pytest to generate explanation message
			'''
			with open(app.config['request_log']) as request_fp:
				request_lines = request_fp.read().split('\n')
			message_lines = []
			year, day = datetime.now().strftime('%Y,%d').split(',')

			for request_line in reversed(request_lines):
				message_lines.insert(0, request_line)

				if request_line.startswith('[') and \
						year in request_line and day in request_line:
					break
			return self.resp_text + ' Request log: ' + \
				'\n'.join(message_lines)

	# status 202 indicates not matched to a Mission
	assert resp.status_code == 202, AssertMsg(resp.text)

	resp = client.post(
		"/update",
		json={
			"irl_time": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"in_game_time": 122.1,
			"soi_name": "Kerbin",
			"vessel_name": "Freighter Alpha Debris",
		}
	)
	assert 200 == resp.status_code

	resp = client.get("/update/_latest")
	assert 200 == resp.status_code
	
	resp = client.post(
		"/update",
		json={
			"irl_time": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"in_game_time": 123.1,
			"soi_name": "Gateway",
			"vessel_name": "Merced",
		}
	)
	assert 200 == resp.status_code


def test_chart_log(app_ctx_chart):
	client = app.test_client()

	data = {
		'in_game_time': 121.183,
		'roll': 3.193,
		'pitch': 45.134,
		'heading': 238.03,
		'velocity': 1234098.3,
		'velocity_h': 1203.1,
		'velocity_v': 12030149.1,
		'altitude_terrain': 55010.3,
		'altitude_sea_level': 55050.0,
		'dv_last_stage': 10505.0,
	}

	resp = client.post(
		"/update",
		json={
			"irl_time": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"soi_name": "Kerbin",
			"vessel_name": "Stayputnik",
		} | data,
	)
	# should not crash and not match a Mission
	assert 202 == resp.status_code

	with open(app_ctx_chart.config['chart_log']) as chart_fp:
		chart_log = chart_fp.read()
	chart_lines = chart_log.split('\n')
	assert 2 == len(chart_lines)
	assert '' == chart_lines[1]
	# build a dict for actual values so the diff is informative
	expected = {k: str(v) for k,v in data.items()}
	actual = {k: v for k,v in 
		zip(data.keys(), chart_lines[0].split(','))}
	assert expected == actual
