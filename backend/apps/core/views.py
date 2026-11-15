from django.shortcuts import render
from django.urls import reverse


def home(request):
    modules = [
        {
            'name': 'Food',
            'description': 'Recipes, nutrition, shopping, and meal prep.',
            'link': reverse('food_today'),
            'coming_soon': False,
        },
        {
            'name': 'Finance',
            'description': 'Budgeting, transactions, and financial analysis.',
            'link': '#',
            'coming_soon': True,
        },
        {
            'name': 'Fitness',
            'description': 'Activity, workouts, and personal progress tracking.',
            'link': '#',
            'coming_soon': True,
        },
        {
            'name': 'AI-assisted Video Editing',
            'description': 'Video planning, media processing, and automation.',
            'link': '#',
            'coming_soon': True,
        },
        {
            'name': 'AI Assistant',
            'description': 'Chat with your local Ollama model.',
            'link': reverse('assistant_chat'),
            'coming_soon': False,
        },
    ]
    return render(request, 'core/home.html', {'modules': modules})
