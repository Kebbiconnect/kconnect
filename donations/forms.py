from django import forms
from .models import Donation, Expense, FinancialReport


class DonationForm(forms.ModelForm):
    """Form for creating/adding new donations"""
    
    class Meta:
        model = Donation
        fields = ['donor_name', 'amount', 'reference', 'notes']
        widgets = {
            'donor_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter donor name'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Bank transaction reference'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Additional notes...',
                'rows': 3
            }),
        }


class ExpenseForm(forms.ModelForm):
    """Form for recording expenses"""
    
    class Meta:
        model = Expense
        fields = ['description', 'amount', 'category', 'date', 'notes']
        widgets = {
            'description': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Description of expense'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Additional details...',
                'rows': 3
            }),
        }


class FinancialReportForm(forms.ModelForm):
    """Form for generating financial reports"""
    
    class Meta:
        model = FinancialReport
        fields = ['title', 'report_period', 'total_income', 'total_expenses', 'summary', 'report_file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Report title'
            }),
            'report_period': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'e.g., January 2025 or Q1 2025'
            }),
            'total_income': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'step': '0.01'
            }),
            'total_expenses': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'step': '0.01'
            }),
            'summary': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Financial summary and key highlights...',
                'rows': 6
            }),
            'report_file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
        }
