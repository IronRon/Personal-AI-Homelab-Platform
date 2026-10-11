from django.shortcuts import render


def food_home(request):
    return render(request, 'food/index.html')
