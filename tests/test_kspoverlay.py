from kspoverlay import app

def test_mission_list():
	client = app.test_client()
	resp = client.get('/mission')
	assert resp.status_code == 200
	assert resp.get_json() == {"mission": []}

	resp = client.post(
		'/mission',
		json={
			'name': 'mission1',
			'start': 1234,
			'last_update': 1245,
			'matcher_priority': 10,
		},
	)
	assert resp.status_code == 302





