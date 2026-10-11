from django.shortcuts import render


def home(request):
    modules = [
        {
            'name': 'Food',
            'description': 'Recipes, nutrition, shopping, and meal prep.',
            'link': '/food/',
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
            'description': 'A local, tool-aware assistant for daily workflows.',
            'link': '#',
            'coming_soon': True,
        },
    ]
    return render(request, 'core/home.html', {'modules': modules})
