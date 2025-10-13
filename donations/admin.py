from django.contrib import admin
from .models import Donation, Expense, FinancialReport, AuditReport


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ['donor_name', 'amount', 'reference', 'status', 'verified_by', 'recorded_by', 'created_at']
    list_filter = ['status', 'created_at', 'verified_at', 'recorded_at']
    search_fields = ['donor_name', 'reference']
    readonly_fields = ['created_at', 'verified_at', 'recorded_at']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'category', 'date', 'recorded_by', 'created_at']
    list_filter = ['category', 'date', 'created_at']
    search_fields = ['description']
    readonly_fields = ['created_at']


@admin.register(FinancialReport)
class FinancialReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_period', 'total_income', 'total_expenses', 'prepared_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['title', 'report_period']
    readonly_fields = ['created_at']


@admin.register(AuditReport)
class AuditReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'audit_period', 'status', 'submitted_by', 'submitted_to', 'submitted_at', 'created_at']
    list_filter = ['status', 'submitted_at', 'created_at']
    search_fields = ['title', 'audit_period', 'findings', 'recommendations']
    readonly_fields = ['created_at', 'submitted_at', 'reviewed_at']
