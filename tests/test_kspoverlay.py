from fixtures import *

from models import KTimestamp, Mission, Matcher, Update, get_db
from kspoverlay import app

from datetime import datetime
import re
from tempfile import NamedTemporaryFile

from pytest import mark

def test_mission_list(app_ctx):
	client = app.test_client()
	resp = client.get('/mission')
	assert 200 == resp.status_code
	assert [] == resp.get_json()

	m1 = Mission({
		"name": "m1", 
		"start": 1, 
		'cur_step': 4,
		'steps': [chr(i) for i in range(97, 104)],
	})
	m1.save()
	m2 = Mission({"name": "m2", "start": 25})
	m2.save()

	actual = client.get("/mission").json
	expected = [
		{
			"uuid": m1.uuid,
			"type": "mission",
			"name": "m1",
			"start": 1.0,
			"url": f"/mission/{m1.uuid}",
			'cur_step': 4,
			'archived': False,
			'steps': [chr(i) for i in range(97, 104)],
		},
		{
			"uuid": m2.uuid,
			"type": "mission",
			"name": "m2",
			"start": 25.0,
			"url": f"/mission/{m2.uuid}",
			'cur_step': None,
			'archived': False,
			'steps': [],
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
	({"irl_time": "abc"}, ['ValueError', 'isoformat', 'irl_time']),
]

@mark.parametrize('request_data,expected_tokens', test_request_log_testdata)
def test_request_log(app_ctx, request_data, expected_tokens):
	client = app.test_client()
	resp = client.post('/update', json=request_data)

	assert 400 == resp.status_code
	with open(app.config['request_log']) as log_fp:
		content = log_fp.read()
		for expected_token in expected_tokens:
			assert expected_token in content


def test_post_update(app_ctx):
	Mission.delete_all()
	Matcher.delete_all()
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
	assert 2 == len(list(Matcher.match_functions()))
	assert 2 == len(list(Mission.iter_all()))

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

	update_dt = '2026-07-03T21:25:56.778929+00:00'
	resp = client.post(
		"/update",
		json={
			"irl_time": update_dt,
			"status": "flight",
			"in_game_time": 122.1,
			"soi_name": "Kerbin",
			"vessel_name": "Freighter Alpha Debris",
		}
	)
	assert 200 == resp.status_code

	update = Update.get_latest()
	assert update.irl_time == datetime.fromisoformat(update_dt).astimezone()
	assert update.soi_name == 'Kerbin'
	
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
