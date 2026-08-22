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

        # 8. Generate & Download PDF
        res_pdf = self.client.get(f'/api/session/{token}/pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, 'application/pdf')
        self.assertTrue(len(res_pdf.data) > 50000)

        # Verify PDF validity with PyMuPDF
        pdf_doc = pymupdf.open(stream=res_pdf.data, filetype='pdf')
        self.assertTrue(len(pdf_doc) >= 5)
        cover_text = pdf_doc[0].get_text()
        self.assertIn('SHAMEER ASSOCIATES', cover_text)
        self.assertIn('Dr. Danish Ahmed', cover_text)

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

if __name__ == '__main__':
    unittest.main()
