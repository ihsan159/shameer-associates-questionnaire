import unittest
import os
import json
import io
import pymupdf
from server import app
import database

class TestShameerAssociatesApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        database.init_db()

    def test_01_schema_and_visuals_endpoints(self):
        res_schema = self.client.get('/api/schema')
        self.assertEqual(res_schema.status_code, 200)
        schema_data = json.loads(res_schema.data)
        self.assertIn('chapters', schema_data)
        self.assertEqual(len(schema_data['chapters']), 8)
        self.assertIn('before_you_begin', schema_data)
        self.assertEqual(len(schema_data['before_you_begin']['thoughts']), 5)

        res_visuals = self.client.get('/api/visuals')
        self.assertEqual(res_visuals.status_code, 200)
        visuals_data = json.loads(res_visuals.data)
        self.assertEqual(len(visuals_data['exterior']), 9)
        self.assertEqual(len(visuals_data['formal_living_dining']), 18)
        self.assertEqual(len(visuals_data['bedroom']), 18)
        self.assertEqual(len(visuals_data['kitchen']), 14)

    def test_02_all_reference_image_files_exist(self):
        with open('static/visual_references.json', 'r', encoding='utf-8') as f:
            visuals = json.load(f)

        for item in visuals['exterior']:
            path = item['image'].lstrip('/')
            self.assertTrue(os.path.exists(path), f"Missing exterior image: {path}")

        for item in visuals['formal_living_dining']:
            liv_path = item['livingImage'].lstrip('/')
            din_path = item['diningImage'].lstrip('/')
            self.assertTrue(os.path.exists(liv_path), f"Missing living image: {liv_path}")
            self.assertTrue(os.path.exists(din_path), f"Missing dining image: {din_path}")

        for item in visuals['bedroom']:
            bed_path = item['bedroomImage'].lstrip('/')
            ward_path = item['wardrobeImage'].lstrip('/')
            self.assertTrue(os.path.exists(bed_path), f"Missing bedroom image: {bed_path}")
            self.assertTrue(os.path.exists(ward_path), f"Missing wardrobe image: {ward_path}")

        for item in visuals['kitchen']:
            path = item['image'].lstrip('/')
            self.assertTrue(os.path.exists(path), f"Missing kitchen image: {path}")

    def test_03_session_lifecycle(self):
        # 1. Create session
        res_new = self.client.post('/api/session/new', json={})
        self.assertEqual(res_new.status_code, 200)
        data_new = json.loads(res_new.data)
        self.assertTrue(data_new['success'])
        token = data_new['token']
        self.assertTrue(len(token) > 10)

        # 2. Save answers
        answers_payload = {
            'client_name': 'Dr. Danish Ahmed',
            'contact_number': '+91 99887 76655',
            'email_address': 'danish.ahmed@example.com',
            'project_location': 'Mampad, Malappuram',
            'project_type': 'New Residence',
            'number_of_floors': 'G + 1',
            'expected_builtup_area': '3800',
            'total_people': 5,
            'living_style': 'Private & calm',
            'total_budget': '₹ 1.8 Cr',
            'natural_light_importance': 'Very important — maximum daylight everywhere',
            'porch_vehicles': '2 cars',
            'formal_living_arrangement': 'Completely separate room',
            'mb_bed_size': 'King (6×6 ft)',
            'mk_layout': 'Island',
            'lighting_mood': 'Warm & cozy',
            'pool_requirement': 'Essential'
        }
        res_save = self.client.post(f'/api/session/{token}/save', json={
            'answers': answers_payload,
            'current_chapter': 2,
            'progress_percent': 45
        })
        self.assertEqual(res_save.status_code, 200)
        data_save = json.loads(res_save.data)
        self.assertTrue(data_save['success'])

        # 3. Save family members
        family_payload = [
            {'user_group': 'Adults', 'count': 2, 'gender': 'Male, Female', 'age_range': '35–40', 'special_note': 'Primary couple'},
            {'user_group': 'Children', 'count': 2, 'gender': 'Boy, Girl', 'age_range': '8, 12', 'special_note': 'Needs study desks'}
        ]
        res_fam = self.client.post(f'/api/session/{token}/save_family', json={'family_members': family_payload})
        self.assertEqual(res_fam.status_code, 200)

        # 4. Save dynamic rooms
        rooms_payload = [
            {
                'room_id': 'room_1',
                'room_name': 'Additional Bedroom 1',
                'answers': {
                    'intended_user': 'Son',
                    'floor_location': 'First floor',
                    'design_style': 'Modern / Minimal',
                    'bed_size': 'Queen (5×6 ft)'
                }
            }
        ]
        res_rooms = self.client.post(f'/api/session/{token}/save_rooms', json={'dynamic_rooms': rooms_payload})
        self.assertEqual(res_rooms.status_code, 200)

        # 5. Save visual selection
        res_vis = self.client.post(f'/api/session/{token}/save_visual', json={
            'category': 'exterior',
            'style': {
                'id': 'ext-01',
                'styleNumber': '01',
                'styleName': 'Modern',
                'image': '/static/references/exterior/01_modern.jpg'
            }
        })
        self.assertEqual(res_vis.status_code, 200)

        # 6. Retrieve session state
        res_get = self.client.get(f'/api/session/{token}')
        self.assertEqual(res_get.status_code, 200)
        session_obj = json.loads(res_get.data)['session']
        self.assertEqual(session_obj['client_name'], 'Dr. Danish Ahmed')
        self.assertEqual(len(session_obj['family_members']), 2)
        self.assertEqual(len(session_obj['dynamic_rooms']), 1)
        self.assertIn('exterior', session_obj['selected_visuals'])

        # 7. Submit session
        res_sub = self.client.post(f'/api/session/{token}/submit')
        self.assertEqual(res_sub.status_code, 200)
        sub_data = json.loads(res_sub.data)
        self.assertEqual(sub_data['status'], 'submitted')

        # 8. Verify public client PDF access is disabled (architect-only feature)
        res_pdf = self.client.get(f'/api/session/{token}/pdf')
        self.assertEqual(res_pdf.status_code, 404)

        # 9. Book consultation
        res_consult = self.client.post(f'/api/session/{token}/consultation', json={
            'date': '2026-09-15',
            'time': '10:00 AM – 11:30 AM',
            'meeting_type': 'In-person Studio Meeting (Kerala)',
            'notes': 'Looking forward to meeting Shameer Associates design team.'
        })
        self.assertEqual(res_consult.status_code, 200)
        consult_data = json.loads(res_consult.data)
        self.assertTrue(consult_data['success'])

    def test_04_architect_auth_and_access_control(self):
        # 1. Unauthenticated access to dashboard should redirect or fail
        res_dash = self.client.get('/architect')
        self.assertIn(res_dash.status_code, (302, 401))

        res_api = self.client.get('/api/architect/projects')
        self.assertIn(res_api.status_code, (302, 401))

        # 2. Invalid login
        res_login_bad = self.client.post('/architect/login', json={
            'email': 'architect@shameerassociates.com',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(res_login_bad.status_code, 401)

        # 3. Valid architect login
        res_login_good = self.client.post('/architect/login', json={
            'email': 'architect@shameerassociates.com',
            'password': 'Architect123!'
        })
        self.assertEqual(res_login_good.status_code, 200)

        # 4. Authenticated access to dashboard & API
        res_dash_auth = self.client.get('/architect')
        self.assertEqual(res_dash_auth.status_code, 200)

        res_projects_auth = self.client.get('/api/architect/projects')
        self.assertEqual(res_projects_auth.status_code, 200)
        proj_data = json.loads(res_projects_auth.data)
        self.assertTrue(proj_data['success'])

        # 5. Logout
        res_logout = self.client.get('/architect/logout')
        self.assertIn(res_logout.status_code, (200, 302))

    def test_05_architect_dashboard_and_workspace_workflow(self):
        # 1. Create client session & submit
        res_new = self.client.post('/api/session/new', json={})
        token = json.loads(res_new.data)['token']

        self.client.post(f'/api/session/{token}/save', json={
            'answers': {
                'client_name': 'Architect Test Client',
                'contact_number': '+91 98765 43210',
                'email_address': 'testclient@shameerassociates.com',
                'project_location': 'Kochi, Kerala',
                'project_type': 'Contemporary Villa'
            }
        })
        self.client.post(f'/api/session/{token}/submit')

        # 2. Architect Login
        self.client.post('/architect/login', json={
            'email': 'architect@shameerassociates.com',
            'password': 'Architect123!'
        })

        # 3. Verify stats
        res_stats = self.client.get('/api/architect/stats')
        self.assertEqual(res_stats.status_code, 200)
        stats = json.loads(res_stats.data)['stats']
        self.assertTrue(stats['total'] >= 1)

        # 4. Get project list & locate project
        res_list = self.client.get('/api/architect/projects?search=Architect%20Test%20Client')
        self.assertEqual(res_list.status_code, 200)
        projects = json.loads(res_list.data)['projects']
        self.assertTrue(len(projects) >= 1)
        project_id = projects[0]['id']

        # 5. Fetch project workspace detail
        res_detail = self.client.get(f'/api/architect/project/{project_id}')
        self.assertEqual(res_detail.status_code, 200)
        detail = json.loads(res_detail.data)['project']
        self.assertEqual(detail['client_name'], 'Architect Test Client')

        # 6. Change project status
        res_status = self.client.post(f'/api/architect/project/{project_id}/status', json={
            'status': 'in_review',
            'note': 'Started preliminary design review'
        })
        self.assertEqual(res_status.status_code, 200)

        # 7. Add internal architect note
        res_note = self.client.post(f'/api/architect/project/{project_id}/note', json={
            'content': 'Client prefers open courtyard layout with maximum north-facing ventilation.',
            'note_type': 'design'
        })
        self.assertEqual(res_note.status_code, 200)
        note_id = json.loads(res_note.data)['note_id']

        # 8. Edit answer
        res_edit = self.client.post(f'/api/architect/project/{project_id}/edit_answer', json={
            'question_id': 'total_budget',
            'new_value': '₹ 2.5 Cr',
            'reason': 'Revised during initial consultation call'
        })
        self.assertEqual(res_edit.status_code, 200)

        # 9. Verify updated detail
        res_detail_updated = self.client.get(f'/api/architect/project/{project_id}')
        updated_detail = json.loads(res_detail_updated.data)['project']
        self.assertEqual(updated_detail['status'], 'in_review')
        self.assertEqual(len(updated_detail['notes']), 1)
        self.assertEqual(updated_detail['answers']['total_budget'], '₹ 2.5 Cr')

        # 10. Generate Architect PDF
        res_arch_pdf = self.client.get(f'/api/architect/project/{project_id}/pdf')
        self.assertEqual(res_arch_pdf.status_code, 200)
        self.assertEqual(res_arch_pdf.mimetype, 'application/pdf')
        self.assertTrue(len(res_arch_pdf.data) > 30000)

        # 11. Delete note
        res_del_note = self.client.delete(f'/api/architect/project/{project_id}/note/{note_id}')
        self.assertEqual(res_del_note.status_code, 200)

    def test_06_security_and_access_control(self):
        # 1. Test that public client cannot access any architect endpoints
        res_arch_pdf_anon = self.client.get('/api/architect/project/1/pdf')
        self.assertIn(res_arch_pdf_anon.status_code, (302, 401))

        res_arch_stats_anon = self.client.get('/api/architect/stats')
        self.assertIn(res_arch_stats_anon.status_code, (302, 401))

        res_arch_proj_anon = self.client.get('/api/architect/projects')
        self.assertIn(res_arch_proj_anon.status_code, (302, 401))

        res_arch_dash_anon = self.client.get('/architect')
        self.assertIn(res_arch_dash_anon.status_code, (302, 401))

        # 2. Test that public PDF route /api/session/<token>/pdf returns 404
        fake_token = "any-random-client-token-12345"
        res_pub_pdf = self.client.get(f'/api/session/{fake_token}/pdf')
        self.assertEqual(res_pub_pdf.status_code, 404)

if __name__ == '__main__':
    unittest.main()

