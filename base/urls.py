from django.urls import path
# from . import views
from . views import TaskList, TaskDetail, TaskCreate, TaskUpdate, TaskDelete, CustomLoginView, RegsiterPage, LandingPageView, UpdateAccountView, UpdatePasswordView,UserListView, BlockUnblockUserView, DashboardView
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [

    path('', LandingPageView.as_view(), name = 'landingpage'),

    path('about/', views.about, name='about'),
    path('services/', views.services, name='services'),
    path('contact/', views.contact, name='contact'),

    path('login/', CustomLoginView.as_view(), name = 'login'),
    path('logout/', LogoutView.as_view(next_page = 'login'), name = 'logout'),
    path('register/', RegsiterPage.as_view(), name = 'register'),

    path('account/update/', UpdateAccountView.as_view(), name='update-account'),
    path('account/password/', UpdatePasswordView.as_view(), name='update-password'),

    path('users/', UserListView.as_view(), name='user-list'),

    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('tasks/', TaskList.as_view(), name = 'tasks'),
    path('task/<int:pk>/', TaskDetail.as_view(), name = 'task'),  #task/<int:pk/ is a primary key
    path('task-create/', TaskCreate.as_view(), name = 'task-create'),
    path('task-update/<int:pk>/', TaskUpdate.as_view(), name = 'task-update'),
    path('task-delete/<int:pk>/', TaskDelete.as_view(), name = 'task-delete'),

    path("users/<int:pk>/toggle-block/", BlockUnblockUserView.as_view(), name="toggle-block"),
    
]