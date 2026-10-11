from django.test import TestCase


class HomePageTests(TestCase):
    def test_home_page_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_food_page_returns_200(self):
        response = self.client.get('/food/')
        self.assertEqual(response.status_code, 200)
