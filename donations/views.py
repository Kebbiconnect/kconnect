from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from staff.decorators import specific_role_required
from .models import Donation, Expense, FinancialReport
from .forms import DonationForm, ExpenseForm, FinancialReportForm


def _monthly_amount_bars(qs, months=6):
    """Bar rows of summed amounts per month, oldest to newest.

    Consistency Rounds C+D: computed only over the queryset the
    calling view already exposes to the role.
    """
    import calendar

    from django.db.models import Sum
    from django.utils import timezone

    from core.dashboard_charts import bar_rows

    now = timezone.now()
    pairs = []
    for back in range(months - 1, -1, -1):
        month = now.month - back
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        total = qs.filter(
            created_at__year=year, created_at__month=month,
        ).aggregate(t=Sum('amount'))['t'] or 0
        pairs.append((f'{calendar.month_abbr[month]} {year}', int(total)))
    return bar_rows(pairs)


def _donation_status_bars(statuses):
    """Counts by status for exactly ``statuses`` — a status outside the
    calling page's own listing never appears, not even at zero."""
    from django.db.models import Count

    from core.dashboard_charts import bar_rows

    counts = dict(
        Donation.objects.filter(status__in=statuses)
        .values_list('status')
        .annotate(n=Count('id'))
    )
    labels = dict(Donation.STATUS_CHOICES)
    return bar_rows([(labels[value], counts.get(value, 0))
                     for value in statuses])


@specific_role_required('Treasurer')
def treasurer_donations(request):
    """Treasurer views unverified donations and can verify them"""
    unverified = Donation.objects.filter(status='UNVERIFIED').order_by('-created_at')
    verified = Donation.objects.filter(status='VERIFIED').order_by('-verified_at')
    
    context = {
        'unverified_donations': unverified,
        'verified_donations': verified,
        # Rounds C+D charts over the full donation register the
        # Treasurer already works with on this page.
        'donation_status_bars': _donation_status_bars(
            ['UNVERIFIED', 'VERIFIED', 'RECORDED']),
        'donation_month_bars': _monthly_amount_bars(Donation.objects.all()),
    }

    return render(request, 'donations/treasurer_donations.html', context)


@specific_role_required('Treasurer')
def verify_donation(request, donation_id):
    """Treasurer verifies a donation"""
    donation = get_object_or_404(Donation, pk=donation_id, status='UNVERIFIED')
    
    if request.method == 'POST':
        donation.status = 'VERIFIED'
        donation.verified_by = request.user
        donation.verified_at = timezone.now()
        donation.save()
        
        messages.success(request, f'Donation from {donation.donor_name} (₦{donation.amount}) has been verified.')
        return redirect('donations:treasurer_donations')
    
    context = {
        'donation': donation,
    }
    
    return render(request, 'donations/verify_donation.html', context)


@specific_role_required('Treasurer')
def add_donation(request):
    """Treasurer can add new donations to the system"""
    if request.method == 'POST':
        form = DonationForm(request.POST)
        if form.is_valid():
            donation = form.save()
            messages.success(request, f'Donation from {donation.donor_name} added successfully.')
            return redirect('donations:treasurer_donations')
    else:
        form = DonationForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'donations/add_donation.html', context)


@specific_role_required('Financial Secretary')
def financial_secretary_donations(request):
    """Financial Secretary views verified donations and can record them"""
    verified = Donation.objects.filter(status='VERIFIED').order_by('-verified_at')
    recorded = Donation.objects.filter(status='RECORDED').order_by('-recorded_at')
    
    context = {
        'verified_donations': verified,
        'recorded_donations': recorded,
        # Rounds C+D charts restricted to the two statuses this page
        # already lists for the Financial Secretary.
        'donation_status_bars': _donation_status_bars(
            ['VERIFIED', 'RECORDED']),
        'donation_month_bars': _monthly_amount_bars(
            Donation.objects.filter(status__in=['VERIFIED', 'RECORDED'])),
    }

    return render(request, 'donations/financial_secretary_donations.html', context)


@specific_role_required('Financial Secretary')
def record_donation(request, donation_id):
    """Financial Secretary records a verified donation"""
    donation = get_object_or_404(Donation, pk=donation_id, status='VERIFIED')
    
    if request.method == 'POST':
        donation.status = 'RECORDED'
        donation.recorded_by = request.user
        donation.recorded_at = timezone.now()
        donation.save()
        
        messages.success(request, f'Donation from {donation.donor_name} (₦{donation.amount}) has been recorded.')
        return redirect('donations:financial_secretary_donations')
    
    context = {
        'donation': donation,
    }
    
    return render(request, 'donations/record_donation.html', context)


@specific_role_required('Financial Secretary')
def expenses_list(request):
    """Financial Secretary views all expenses"""
    expenses = Expense.objects.all().order_by('-date', '-created_at')
    
    total_expenses = sum(expense.amount for expense in expenses)
    
    context = {
        'expenses': expenses,
        'total_expenses': total_expenses,
    }
    
    return render(request, 'donations/expenses_list.html', context)


@specific_role_required('Financial Secretary')
def add_expense(request):
    """Financial Secretary records a new expense"""
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.recorded_by = request.user
            expense.save()
            
            messages.success(request, f'Expense "{expense.description}" (₦{expense.amount}) recorded successfully.')
            return redirect('donations:expenses_list')
    else:
        form = ExpenseForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'donations/add_expense.html', context)


@specific_role_required('Financial Secretary')
def financial_reports(request):
    """View all financial reports"""
    reports = FinancialReport.objects.all().order_by('-created_at')

    context = {
        'reports': reports,
        # Rounds C+D charts: recorded income and expenses by month —
        # the same totals the create-report flow already sums for
        # this role.
        'income_month_bars': _monthly_amount_bars(
            Donation.objects.filter(status='RECORDED')),
        'expense_month_bars': _monthly_amount_bars(Expense.objects.all()),
    }

    return render(request, 'donations/financial_reports.html', context)


@specific_role_required('Financial Secretary')
def create_financial_report(request):
    """Create a new financial report"""
    if request.method == 'POST':
        form = FinancialReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.prepared_by = request.user
            report.save()
            
            messages.success(request, f'Financial report "{report.title}" created successfully.')
            return redirect('donations:financial_reports')
    else:
        total_donations = sum(
            d.amount for d in Donation.objects.filter(status='RECORDED')
        )
        total_expenses = sum(e.amount for e in Expense.objects.all())
        
        form = FinancialReportForm(initial={
            'total_income': total_donations,
            'total_expenses': total_expenses,
        })
    
    context = {
        'form': form,
    }
    
    return render(request, 'donations/create_financial_report.html', context)
