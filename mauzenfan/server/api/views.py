from django.shortcuts import render # Kept for potential future use
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .serializers import UserRegistrationSerializer # Ensure this import is correct

class RegistrationView(APIView):
    permission_classes = [AllowAny] # Anyone can register

    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # You might want to return more user data or a token here in a real app
            return Response({"message": "User registered successfully.", "user_id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
