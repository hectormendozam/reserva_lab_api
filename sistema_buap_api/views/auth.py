from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from sistema_buap_api import models, serializers


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = models.User.USERNAME_FIELD

    def validate(self, attrs):
        if 'username' in attrs and 'email' not in attrs:
            attrs['email'] = attrs.pop('username')
        return super().validate(attrs)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        if 'username' in data and 'email' not in data:
            data['email'] = data['username']
        
        request._full_data = data
        
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            email = data.get('email') or data.get('username')
            user = models.User.objects.filter(email=email).first()
            
            if user:
                user_data = serializers.UserSerializer(user).data
                response_data = response.data.copy() if isinstance(response.data, dict) else {}
                response_data.update({
                    'user': user_data,
                    'token': response_data.get('access'),  
                    'role': user.role.lower(),  
                })
                response.data = response_data
        
        return response


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        if 'student_id' in data and 'matricula' not in data:
            data['matricula'] = data.pop('student_id')
        
        if 'role' in data:
            role_map = {
                'ADMIN': models.User.UserRole.ADMIN,
                'TECH': models.User.UserRole.TECNICO,
                'TECNICO': models.User.UserRole.TECNICO,
                'ESTUDIANTE': models.User.UserRole.ESTUDIANTE,
                'alumno': models.User.UserRole.ESTUDIANTE,
                'tecnico': models.User.UserRole.TECNICO,
                'administrador': models.User.UserRole.ADMIN,
            }
            data['role'] = role_map.get(data['role'], models.User.UserRole.ESTUDIANTE)
        
        serializer = serializers.UserRegistrationSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        data = serializers.UserProfileSerializer(user).data
        return Response(data, status=status.HTTP_201_CREATED)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = serializers.UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = serializers.UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
