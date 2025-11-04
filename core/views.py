from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from campaigns.models import Campaign
from media.models import MediaItem
from staff.models import User
from leadership.models import Zone, LGA, Ward
from .models import FAQ, Report
from .forms import WardReportForm, LGAReportForm, ZonalReportForm, ReportReviewForm
from staff.decorators import approved_leader_required

def home(request):
    featured_campaigns = Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')[:3]
    latest_news = Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')[:6]
    context = {
        'featured_campaigns': featured_campaigns,
        'latest_news': latest_news,
    }
    return render(request, 'core/home.html', context)

def about(request):
    return render(request, 'core/about.html')

def leadership(request):
    zone_filter = request.GET.get('zone')
    lga_filter = request.GET.get('lga')
    ward_filter = request.GET.get('ward')
    
    from leadership.models import RoleDefinition
    
    leadership_positions = []
    
    # Case 1: Default - Show only State Executive roles (20 roles)
    if not zone_filter and not lga_filter and not ward_filter:
        state_roles = RoleDefinition.objects.filter(tier='STATE').order_by('seat_number')
        for role in state_roles:
            holder = User.objects.filter(
                role_definition=role, 
                status='APPROVED',
                is_superuser=False
            ).first()
            leadership_positions.append({
                'role': role,
                'holder': holder,
                'vacant': holder is None
            })
    
    # Case 2: Only Zone selected - Show Zonal roles for that zone
    elif zone_filter and not lga_filter and not ward_filter:
        zone = Zone.objects.get(id=zone_filter)
        
        zonal_roles = RoleDefinition.objects.filter(tier='ZONAL').order_by('seat_number')
        for role in zonal_roles:
            holder = User.objects.filter(
                role_definition=role, 
                zone=zone, 
                status='APPROVED',
                is_superuser=False
            ).first()
            leadership_positions.append({
                'role': role,
                'holder': holder,
                'zone': zone,
                'vacant': holder is None
            })
    
    # Case 3: Only LGA selected - Show LGA roles for that LGA
    elif lga_filter and not zone_filter and not ward_filter:
        lga = LGA.objects.get(id=lga_filter)
        
        lga_roles = RoleDefinition.objects.filter(tier='LGA').order_by('seat_number')
        for role in lga_roles:
            holder = User.objects.filter(
                role_definition=role, 
                lga=lga, 
                status='APPROVED',
                is_superuser=False
            ).first()
            leadership_positions.append({
                'role': role,
                'holder': holder,
                'lga': lga,
                'vacant': holder is None
            })
    
    # Case 4: Only Ward selected - Show Ward roles for that ward
    elif ward_filter and not zone_filter and not lga_filter:
        ward = Ward.objects.get(id=ward_filter)
        
        ward_roles = RoleDefinition.objects.filter(tier='WARD').order_by('seat_number')
        for role in ward_roles:
            holder = User.objects.filter(
                role_definition=role, 
                ward=ward, 
                status='APPROVED',
                is_superuser=False
            ).first()
            leadership_positions.append({
                'role': role,
                'holder': holder,
                'ward': ward,
                'vacant': holder is None
            })
    
    # Case 5: Multiple filters - Show roles based on filter combination
    elif zone_filter or lga_filter or ward_filter:
        zone = Zone.objects.get(id=zone_filter) if zone_filter else None
        lga = LGA.objects.get(id=lga_filter) if lga_filter else None
        ward = Ward.objects.get(id=ward_filter) if ward_filter else None
        
        # Determine which lga and zone to use if not directly provided
        if ward and not lga:
            lga = ward.lga
        if lga and not zone:
            zone = lga.zone
        if ward and not zone:
            zone = ward.lga.zone
        
        # Determine which tiers to show based on filter combination
        # Zone only → Zonal roles only
        # LGA only → LGA roles only
        # Ward only → Ward roles only
        # Zone + LGA → Zonal + LGA roles
        # LGA + Ward → LGA + Ward roles
        # Zone + LGA + Ward → State + Zonal + LGA + Ward roles (all tiers)
        show_state = zone_filter and lga_filter and ward_filter
        show_zonal = bool(zone_filter)
        show_lga = bool(lga_filter)
        show_ward = bool(ward_filter)
        
        # Add State Executive roles only if all three filters are selected
        # Show positions filled in that location + statewide leaders (NULL geography)
        # Hide vacant positions for executives not in the filtered location
        if show_state:
            state_roles = RoleDefinition.objects.filter(tier='STATE').order_by('seat_number')
            for role in state_roles:
                holder_query = User.objects.filter(
                    role_definition=role, 
                    status='APPROVED',
                    is_superuser=False
                )
                
                # Build location filter for state executives
                # Include: 1) Executives in the filtered location (zone or LGA match)
                #         2) Statewide leaders with NULL geography (e.g., President)
                location_filter = Q(zone__isnull=True, lga__isnull=True)  # Statewide leaders
                if zone:
                    location_filter |= Q(zone=zone)
                if lga:
                    location_filter |= Q(lga=lga)
                
                # Apply location filter
                holder_query = holder_query.filter(location_filter)
                holder = holder_query.first()
                
                # Only add if position is filled (no vacant positions for state executives in filtered view)
                if holder:
                    leadership_positions.append({
                        'role': role,
                        'holder': holder,
                        'vacant': False
                    })
        
        # Add Zonal roles if zone is specified
        if show_zonal and zone:
            zonal_roles = RoleDefinition.objects.filter(tier='ZONAL').order_by('seat_number')
            for role in zonal_roles:
                holder = User.objects.filter(
                    role_definition=role, 
                    zone=zone, 
                    status='APPROVED',
                    is_superuser=False
                ).first()
                leadership_positions.append({
                    'role': role,
                    'holder': holder,
                    'zone': zone,
                    'vacant': holder is None
                })
        
        # Add LGA roles if lga is specified
        if show_lga and lga:
            lga_roles = RoleDefinition.objects.filter(tier='LGA').order_by('seat_number')
            for role in lga_roles:
                holder = User.objects.filter(
                    role_definition=role, 
                    lga=lga, 
                    status='APPROVED',
                    is_superuser=False
                ).first()
                leadership_positions.append({
                    'role': role,
                    'holder': holder,
                    'lga': lga,
                    'vacant': holder is None
                })
        
        # Add Ward roles if ward is specified
        if show_ward and ward:
            ward_roles = RoleDefinition.objects.filter(tier='WARD').order_by('seat_number')
            for role in ward_roles:
                holder = User.objects.filter(
                    role_definition=role, 
                    ward=ward, 
                    status='APPROVED',
                    is_superuser=False
                ).first()
                leadership_positions.append({
                    'role': role,
                    'holder': holder,
                    'ward': ward,
                    'vacant': holder is None
                })
    
    zones = Zone.objects.all()
    lgas = LGA.objects.select_related('zone').all()
    wards = Ward.objects.select_related('lga').all()
    
    context = {
        'leadership_positions': leadership_positions,
        'zones': zones,
        'lgas': lgas,
        'wards': wards,
        'selected_zone': zone_filter,
        'selected_lga': lga_filter,
        'selected_ward': ward_filter,
    }
    return render(request, 'core/leadership.html', context)

def view_profile(request, user_id):
    profile_user = get_object_or_404(User, id=user_id, status='APPROVED', is_superuser=False)
    
    context = {
        'profile_user': profile_user,
    }
    return render(request, 'core/view_profile.html', context)

def campaigns(request):
    all_campaigns = Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')
    context = {
        'campaigns': all_campaigns,
    }
    return render(request, 'core/campaigns.html', context)

def campaign_detail(request, slug):
    campaign = get_object_or_404(Campaign, slug=slug, status='PUBLISHED')
    campaign.views += 1
    campaign.save(update_fields=['views'])
    
    related_campaigns = Campaign.objects.filter(status='PUBLISHED').exclude(id=campaign.id).order_by('-published_at')[:3]
    
    context = {
        'campaign': campaign,
        'related_campaigns': related_campaigns,
    }
    return render(request, 'core/campaign_detail.html', context)

def gallery(request):
    media_type = request.GET.get('type', 'all')
    
    media_items = MediaItem.objects.filter(status='APPROVED')
    
    if media_type == 'PHOTO':
        media_items = media_items.filter(media_type='PHOTO')
    elif media_type == 'VIDEO':
        media_items = media_items.filter(media_type='VIDEO')
    
    media_items = media_items.order_by('-created_at')
    
    context = {
        'media_items': media_items,
        'selected_type': media_type,
    }
    return render(request, 'core/gallery.html', context)

def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        
        try:
            email_subject = f'KPN Contact Form: Message from {name}'
            email_body = f"""
New contact form submission from KPN website:

Name: {name}
Email: {email}

Message:
{message}

---
This message was sent via the KPN contact form.
            """
            
            send_mail(
                subject=email_subject,
                message=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['kpn.kebbi@gmail.com'],
                fail_silently=False,
            )
            
            messages.success(request, 'Thank you for contacting us! We will get back to you soon.')
        except Exception as e:
            messages.error(request, 'There was an error sending your message. Please try again later or contact us directly via email.')
        
        return redirect('core:contact')
    
    return render(request, 'core/contact.html')

def support_us(request):
    return render(request, 'core/support_us.html')

def faq(request):
    faqs = FAQ.objects.filter(is_active=True)
    context = {
        'faqs': faqs,
    }
    return render(request, 'core/faq.html', context)

def code_of_conduct(request):
    return render(request, 'core/code_of_conduct.html')


@login_required
@approved_leader_required
def submit_report(request):
    """Hierarchical report submission view"""
    user = request.user
    
    if user.role == 'WARD':
        FormClass = WardReportForm
        report_type = 'WARD_TO_LGA'
        if not user.ward:
            messages.error(request, 'Your ward assignment is missing. Please contact the administrator.')
            return redirect('staff:dashboard')
        lga_coordinator = User.objects.filter(
            role='LGA',
            lga=user.ward.lga,
            role_definition__title='LGA Coordinator',
            status='APPROVED'
        ).first()
        submitted_to = lga_coordinator
    elif user.role == 'LGA':
        FormClass = LGAReportForm
        report_type = 'LGA_TO_ZONAL'
        if not user.lga:
            messages.error(request, 'Your LGA assignment is missing. Please contact the administrator.')
            return redirect('staff:dashboard')
        zonal_coordinator = User.objects.filter(
            role='ZONAL',
            zone=user.lga.zone,
            role_definition__title='Zonal Coordinator',
            status='APPROVED'
        ).first()
        submitted_to = zonal_coordinator
    elif user.role == 'ZONAL':
        FormClass = ZonalReportForm
        report_type = 'ZONAL_TO_STATE'
        state_supervisor = User.objects.filter(
            role='STATE',
            role_definition__title='State Supervisor',
            status='APPROVED'
        ).first()
        submitted_to = state_supervisor
    else:
        messages.error(request, 'Report submission is only available for Ward, LGA, and Zonal leaders.')
        return redirect('staff:dashboard')
    
    if not submitted_to:
        messages.error(request, f'No supervisor found to submit the report to. Please contact the administrator.')
        return redirect('staff:dashboard')
    
    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.submitted_by = user
            report.submitted_to = submitted_to
            report.report_type = report_type
            report.status = 'SUBMITTED'
            report.submitted_at = timezone.now()
            report.save()
            
            _send_report_notification(report, 'submitted')
            
            messages.success(request, f'Report submitted successfully to {submitted_to.get_full_name()}!')
            return redirect('staff:dashboard')
    else:
        form = FormClass()
    
    context = {
        'form': form,
        'report_type': report_type,
        'submitted_to': submitted_to,
    }
    return render(request, 'core/submit_report.html', context)


@login_required
@approved_leader_required
def review_report(request, report_id):
    """Supervisor report review view"""
    report = get_object_or_404(Report, id=report_id)
    user = request.user
    
    is_president = user.role_definition and user.role_definition.title == 'President'
    if report.submitted_to != user and not is_president:
        messages.error(request, 'You do not have permission to review this report.')
        return redirect('staff:dashboard')
    
    if request.method == 'POST':
        form = ReportReviewForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save(commit=False)
            action = request.POST.get('action')
            report.status = action
            report.is_reviewed = True
            report.reviewed_by = user
            report.reviewed_at = timezone.now()
            report.save()
            
            action_text = {
                'APPROVED': 'approved',
                'FLAGGED': 'flagged for issues',
                'REJECTED': 'rejected'
            }.get(action, 'reviewed')
            
            _send_report_notification(report, 'reviewed')
            
            if action == 'APPROVED' and report.can_be_escalated():
                escalated_report = _escalate_report(report, user)
                if escalated_report:
                    _send_report_notification(escalated_report, 'submitted')
                    messages.success(
                        request, 
                        f'Report approved and escalated to {escalated_report.submitted_to.get_full_name()}!'
                    )
                else:
                    messages.warning(
                        request, 
                        f'Report approved but could not be escalated - no supervisor found for the next level. Please contact the administrator to ensure all coordinator positions are filled.'
                    )
            else:
                messages.success(request, f'Report has been {action_text} successfully!')
            
            return redirect('staff:dashboard')
    else:
        form = ReportReviewForm(instance=report)
    
    context = {
        'report': report,
        'form': form,
    }
    return render(request, 'core/review_report.html', context)


def _escalate_report(original_report, reviewer):
    """
    Create an escalated report to the next level in the hierarchy.
    Ward → LGA → Zonal → State
    
    Uses the original submitter's geography (ward/LGA/zone) to determine the next supervisor,
    ensuring escalation works even when President or others without zone data review.
    """
    if original_report.report_type == 'WARD_TO_LGA':
        next_report_type = 'LGA_TO_ZONAL'
        
        submitter = original_report.submitted_by
        submitter_zone = submitter.zone
        
        if not submitter_zone and submitter.ward:
            if submitter.ward.lga and submitter.ward.lga.zone:
                submitter_zone = submitter.ward.lga.zone
        
        if not submitter_zone and submitter.lga:
            if submitter.lga.zone:
                submitter_zone = submitter.lga.zone
        
        if not submitter_zone:
            return None
        
        next_supervisor = User.objects.filter(
            role='ZONAL',
            zone=submitter_zone,
            role_definition__title='Zonal Coordinator',
            status='APPROVED'
        ).first()
    elif original_report.report_type == 'LGA_TO_ZONAL':
        next_report_type = 'ZONAL_TO_STATE'
        next_supervisor = User.objects.filter(
            role='STATE',
            role_definition__title='State Supervisor',
            status='APPROVED'
        ).first()
    else:
        return None
    
    if not next_supervisor:
        return None
    
    actual_submitter = original_report.submitted_to if original_report.submitted_to else reviewer
    
    escalated_report = Report.objects.create(
        title=f"Consolidated {original_report.get_report_type_display()} - {original_report.period}",
        report_type=next_report_type,
        content=f"[Escalated from {original_report.submitted_to.get_full_name() if original_report.submitted_to else reviewer.get_full_name()}]\n[Approved by: {reviewer.get_full_name()}]\n\n{original_report.content}",
        period=original_report.period,
        submitted_by=actual_submitter,
        submitted_to=next_supervisor,
        parent_report=original_report,
        status='SUBMITTED',
        submitted_at=timezone.now(),
        deadline=original_report.deadline
    )
    
    original_report.is_escalated = True
    original_report.escalated_at = timezone.now()
    original_report.status = 'ESCALATED'
    original_report.save()
    
    return escalated_report


def _send_report_notification(report, notification_type):
    """Send email notification for report submission or review"""
    try:
        if notification_type == 'submitted':
            if report.submitted_to and report.submitted_to.email:
                subject = f'New Report Submitted: {report.title}'
                message = f"""
Dear {report.submitted_to.get_full_name()},

A new report has been submitted for your review:

Title: {report.title}
Period: {report.period}
Submitted by: {report.submitted_by.get_full_name()}
Report Type: {report.get_report_type_display()}
Deadline: {report.deadline if report.deadline else 'Not set'}

Please log in to the KPN platform to review this report.

Best regards,
KPN Management System
                """
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [report.submitted_to.email],
                    fail_silently=True,
                )
        
        elif notification_type == 'reviewed':
            if report.submitted_by and report.submitted_by.email:
                status_text = report.get_status_display()
                subject = f'Report {status_text}: {report.title}'
                message = f"""
Dear {report.submitted_by.get_full_name()},

Your report has been reviewed:

Title: {report.title}
Status: {status_text}
Reviewed by: {report.reviewed_by.get_full_name() if report.reviewed_by else 'N/A'}
Review Notes: {report.review_notes if report.review_notes else 'No notes provided'}

Please log in to the KPN platform to view the full details.

Best regards,
KPN Management System
                """
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [report.submitted_by.email],
                    fail_silently=True,
                )
    except Exception as e:
        pass
