from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.contrib.auth import authenticate, get_user_model
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer, 
    ChangePasswordSerializer, UserLoginSerializer
)
from utils.permissions import IsOwnerOrAdmin

User = get_user_model()

class UserRegisterView(generics.CreateAPIView):
    """View for user registration."""
    
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = UserCreateSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'data': {
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            },
            'message': 'User registered successfully.',
            'errors': []
        }, status=status.HTTP_201_CREATED)

class UserLoginView(APIView):
    """View for user login."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'success': True,
                'data': {
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                },
                'message': 'User logged in successfully.',
                'errors': []
            })
        else:
            return Response({
                'success': False,
                'data': {},
                'message': 'Invalid credentials.',
                'errors': ['Invalid email or password.']
            }, status=status.HTTP_401_UNAUTHORIZED)

class UserLogoutView(APIView):
    """View for user logout."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response({
                'success': True,
                'data': {},
                'message': 'User logged out successfully.',
                'errors': []
            })
        except Exception as e:
            return Response({
                'success': False,
                'data': {},
                'message': 'Logout failed.',
                'errors': [str(e)]
            }, status=status.HTTP_400_BAD_REQUEST)

class UserDetailsView(generics.RetrieveUpdateAPIView):
    """View for retrieving and updating user details."""
    
    permission_classes = (permissions.IsAuthenticated, IsOwnerOrAdmin)
    serializer_class = UserSerializer
    
    def get_object(self):
        return self.request.user
    
    def get(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user)
        
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'User details retrieved successfully.',
            'errors': []
        })
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        user = self.get_object()
        serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'success': True,
            'data': UserSerializer(user).data,
            'message': 'User details updated successfully.',
            'errors': []
        })

class ChangePasswordView(APIView):
    """View for changing user's password."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        
        # Check old password
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({
                'success': False,
                'data': {},
                'message': 'Password change failed.',
                'errors': ['Old password is incorrect.']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set new password
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({
            'success': True,
            'data': {},
            'message': 'Password changed successfully.',
            'errors': []
        })