from django.urls import path
from .views import RegistrationView # Import the view
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('auth/register/', RegistrationView.as_view(), name='user-register'),
    path('auth/login/', obtain_auth_token, name='user-login'),
]
