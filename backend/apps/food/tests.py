from django.test import SimpleTestCase


class FoodPageTests(SimpleTestCase):
    def test_food_page_returns_200(self):
        response = self.client.get('/food/')
        self.assertEqual(response.status_code, 200)
