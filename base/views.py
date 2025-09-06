from django.shortcuts import render, redirect
# from django.http import HttpResponse
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView, FormView
from django.views.generic import TemplateView

from django.urls import reverse_lazy

from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User

#For Blocking and Unblocking Users
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views import View

from .models import Task
from .models import ActivityLog

#Main Dashboard
class DashboardView(LoginRequiredMixin, ListView):
    model = Task
    context_object_name = 'tasks'
    template_name = 'dashboard/dashboard.html'  # new template for dashboard

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = context['tasks'].filter(user=self.request.user)
        context['count'] = context['tasks'].filter(complete=False).count()

        search_input = self.request.GET.get('search-area') or ''
        if search_input:
            context['tasks'] = context['tasks'].filter(title__icontains=search_input)

        context['search_input'] = search_input
        return context

#Seaching for a certain User
class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = "registration/userlist.html"
    context_object_name = "users"    

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser # Only allow managers (superusers or staff)

    def get_queryset(self):
        queryset = super().get_queryset()
        search_input = self.request.GET.get("search") or ""
        if search_input:
            queryset = queryset.filter(username__icontains=search_input)
        return queryset
        
# Updating User Information
class UpdateAccountView(LoginRequiredMixin,UpdateView):
    model = User
    fields = ['username', 'email'] #Editable fields when updating user info
    template_name = 'registration/updateaccount.html'
    success_url = reverse_lazy('dashboard')
    
    def get_object(self):
        return self.request.user

#Updating User Password
class UpdatePasswordView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'registration/updatepassword.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)

        
        update_session_auth_hash(self.request, form.user) # Keep the user logged in after password change
        return response
    

#Blocking Users 
class BlockUnblockUserView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        
        if user == request.user:
            messages.error(request, "You cannot block yourself.")
            return redirect("user-list")

        user.is_active = not user.is_active
        user.save()

        action = "unblocked" if user.is_active else "blocked"
        # Uncomment once the DATABASE is made
        # ActivityLog.objects.create(
        #     user=request.user,
        #     action=f"{action.capitalize()} account: {user.username}"
        # )

        messages.success(request, f"User {user.username} has been {action}.")
        return redirect("user-list")

# Landing Page View
class LandingPageView(TemplateView):
    template_name = 'landingpage/landingpage.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('tasks')
        return super().dispatch(request, *args, **kwargs)

# Login Page View
class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('tasks')

# Registration Page View
class RegsiterPage(FormView):
    template_name = 'registration/register.html'
    form_class = UserCreationForm
    redirect_authenticated_user = True
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        user = form.save()
        if user is not None:
            login(self.request, user)
        return super(RegsiterPage, self).form_valid(form)

    def get(self,*args,**kwargs):
        if self.request.user.is_authenticated:
            return redirect('tasks') 
        return super(RegsiterPage, self).get(*args, **kwargs)

# Main Dashboard as of now
class TaskList(LoginRequiredMixin, ListView):
    # return HttpResponse('To Do List')
    model = Task
    context_object_name = 'tasks'                           #change name for object_list for ease of use
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):                   #restricting user to their own data
        context = super().get_context_data(**kwargs)
        context['tasks'] = context['tasks'].filter(user = self.request.user)
        context['count'] = context['tasks'].filter(complete = False).count()

        search_input = self.request.GET.get('search-area') or ''
        if search_input:
            context['tasks'] = context['tasks'].filter(title__icontains = search_input)         #any word can be seach aslong as it have the letter your searching
            # context['tasks'] = context['tasks'].filter(title__startswith = search_input)        #only the 1st word and its letter can be search

        context['search_input'] = search_input

        return context

# List of all the Tasks
class TaskDetail(LoginRequiredMixin, DetailView):
    model = Task
    context_object_name = 'task'              
    template_name = 'base/task.html'

# Creation of Tasks
class TaskCreate(LoginRequiredMixin, CreateView):
    model = Task
    fields = ['title', 'description', 'complete']
    success_url = reverse_lazy('dashboard')

    # def form_valid(self, form):
    #     form.instance.user = self.request.user
    #     return super(TaskCreate, self).form_valid(form)

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)

        # Uncomment once the DATABASE is made
        # Log the action
        # ActivityLog.objects.create(
        #     user=self.request.user,
        #     action=f"Created task: {form.instance.title}"
        # )

        return response

# Updating of Existing Tasks
class TaskUpdate(LoginRequiredMixin, UpdateView):
    model = Task
    fields = ['title', 'description', 'complete']
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)

        # Uncomment once the DATABASE is made
        # ActivityLog.objects.create(
        #     user=self.request.user,
        #     action=f"Updated task: {form.instance.title}"
        # )

        return response

# Deleting of Existing Tasks
class TaskDelete(LoginRequiredMixin, DeleteView):
    model = Task
    context_object_name = 'task'
    success_url = reverse_lazy('dashboard')

    def delete(self, request, *args, **kwargs):
        task = self.get_object()

        # Uncomment once the DATABASE is made
        # ActivityLog.objects.create(
        #     user=self.request.user,
        #     action=f"Deleted task: {task.title}"
        # )
        return super().delete(request, *args, **kwargs)


# Place holder for the landing pages
def about(request):
    return render(request, "landingpage/about.html")

def services(request):
    return render(request, "landingpage/services.html")

def contact(request):
    return render(request, "landingpage/contact.html")
