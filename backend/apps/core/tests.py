from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_page_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('food_today'))

    def test_food_page_returns_200(self):
        response = self.client.get('/food/')
        self.assertEqual(response.status_code, 200)
