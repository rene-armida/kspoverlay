from models import KTimestamp, Mission, Matcher, get_db
from kspoverlay import app

from pytest import fixture, mark

@fixture(name="app_ctx")
def get_app_and_fresh_db():
	with app.app_context() as the_app:
		get_db(reset=True) # recreate the database
	
		yield the_app

def test_mission_list(app_ctx):
	client = app.test_client()
	resp = client.get('/mission')
	assert 200 == resp.status_code
	assert [] == resp.get_json()

	m1 = Mission({"name": "m1", "start": 1, "last_update": 1000})
	m1.save()
	m2 = Mission({"name": "m2"})
	m2.save()

	actual = client.get("/mission").json
	del actual[0]['id']
	del actual[1]['id']
	expected = [
		{
			"uuid": m1["uuid"],
			"type": "mission",
			"name": "m1",
			"start": 'Y1D001 0:00:01',
			"last_update": 'Y1D001 0:16:40',
			"mission_elapsed_time": '0:16:39',
			"url": f"/mission/{m1['uuid']}",
		},
		{
			"uuid": m2["uuid"],
			"type": "mission",
			"name": "m2",
			"start": None,
			"last_update": None,
			"mission_elapsed_time": None,
			"url": f"/mission/{m2['uuid']}",
		}
	]
	assert expected == actual

def test_mission_get(app_ctx):
	client = app.test_client()
	Mission({"name": "m1", "last_update": 1}).save()
	Mission({"name": "m2", "last_update": 1000}).save()
	m = Mission.find_one(name="m2")
	assert m.as_dict() == client.get(f"/mission/{m['uuid']}").json


def test_post_update_not_json(app_ctx):
	client = app.test_client()
	resp = client.post("/update", "blah")
	assert resp.status_code == 400

def test_post_update_bad_structure(app_ctx):
	client = app.test_client()
	resp = client.post(
		"/update",
		json={
			"date": '2026-07-03T21:25:56.778929+00:00',
			"status": "meep", # bad status value
			"data": {
				"in_game_time": 121,
				"soi_name": "Kerbin",
				"vessel_name": "Stayputnik",
			}
		}
	)
	assert resp.status_code == 400

	resp = client.post(
		"/update",
		json={"woop": "abc"} # missing expected keys
	)
	assert resp.status_code == 400

def test_bad_request_log(app_ctx):
	client = app.test_client()
	resp = client.post(
		'/update',
		json={
			"date": "abc",
		}
	)

	assert resp.status_code == 400
	with open(app.config['bad_request_log']) as log_fp:
		content = log_fp.read()
		assert 'ValueError' in content
		assert 'date' in content


@mark.xfail
def test_post_update_unexpected_game_data(app_ctx):
	'''
	not implemented - unexpected game data keys are ignored
	'''
	client = app_ctx.test_client()
	resp = client.post(
		"/update",
		json={
			"date": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"data": {
				"derp": 121, #unexpected game data key
			}
		}
	)
	assert resp.status_code == 400


def test_post_update(app_ctx):
	m1 = Mission({"name": "m1"})
	m1.save()
	m2 = Mission({"name": "m2"})
	m2.save()
	Matcher({
		"vessel": "Freighter Alpha.*", 
		"mission_uuid": m1["uuid"],
	}).save()
	Matcher({
		"soi_name": "Gateway",
		"mission_uuid": m2["uuid"],
	}).save()

	client = app.test_client()
	resp = client.post(
		"/update",
		json={
			"date": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"data": {
				"InGameTime": 121.183,
				"BodyName": "Kerbin",
				"VesselName": "Stayputnik",
			}
		}
	)
	assert resp.status_code == 202, resp.text # ignored

	resp = client.post(
		"/update",
		json={
			"date": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"data": {
				"InGameTime": 122.1,
				"BodyName": "Kerbin",
				"VesselName": "Freighter Alpha Debris",
			}
		}
	)
	assert resp.status_code == 302
	# let's follow the response to verify name
	assert "m1" == client.get(resp.location).json["name"]

	resp = client.post(
		"/update",
		json={
			"date": '2026-07-03T21:25:56.778929+00:00',
			"status": "flight",
			"data": {
				"InGameTime": 123.1,
				"BodyName": "Gateway",
				"VesselName": "Merced",
			}
		}
	)
	assert resp.status_code == 302
	# let's follow the response to verify name
	assert "m2" == client.get(resp.location).json["name"]

	assert Mission.find_one(name="m1")["last_update"] == KTimestamp(122.1)
	assert Mission.find_one(name="m2")["last_update"] == KTimestamp(123.1)
