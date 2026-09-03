"""
URL configuration for drilling_scheduler project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.shortcuts import render

# Custom logout view that actually logs out on GET request
def custom_logout_view(request):
    """
    Custom logout view that properly clears the session on GET requests.
    Django 5.x LogoutView only logs out on POST, so we need this custom view.
    """
    # Actually perform the logout - this clears the session
    auth_logout(request)
    # Render the logged out template
    return render(request, 'registration/logged_out.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', custom_logout_view, name='logout'),
    path('', include('scheduler.urls')),
]

# Serve static and media files
# For production, use a proper web server (nginx/Apache) or whitenoise
# For development/testing, Django can serve these files
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
