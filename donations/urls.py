from django.urls import path
from . import views

app_name = 'donations'

urlpatterns = [
    path('treasurer/', views.treasurer_donations, name='treasurer_donations'),
    path('treasurer/add/', views.add_donation, name='add_donation'),
    path('treasurer/verify/<int:donation_id>/', views.verify_donation, name='verify_donation'),
    
    path('financial-secretary/', views.financial_secretary_donations, name='financial_secretary_donations'),
    path('financial-secretary/record/<int:donation_id>/', views.record_donation, name='record_donation'),
    
    path('expenses/', views.expenses_list, name='expenses_list'),
    path('expenses/add/', views.add_expense, name='add_expense'),
    
    path('reports/', views.financial_reports, name='financial_reports'),
    path('reports/create/', views.create_financial_report, name='create_financial_report'),
]
