from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q, F
from django.core.paginator import Paginator
from campaigns.models import Campaign
from media.models import MediaItem
from staff.models import User
from leadership.models import Zone, LGA, Ward
from .models import FAQ, Report, Opportunity
from .forms import WardReportForm, LGAReportForm, ZonalReportForm, ReportReviewForm
from staff.decorators import approved_leader_required

def home(request):
    from .models import AdvocacyCampaign
    featured_campaigns = AdvocacyCampaign.objects.filter(is_active=True).order_by('-created_at')[:3]
    latest_news = Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')[:6]
    latest_opportunities = Opportunity.objects.filter(
        status__in=['OPEN', 'CLOSING_SOON']
    ).filter(Q(deadline__isnull=True) | Q(deadline__gte=timezone.localdate())).order_by(
        F('deadline').asc(nulls_last=True), '-created_at'
    )[:3]
    # Network figures, computed exactly as the Impact page computes
    # them (core.metrics.headline_figures). Priority 5 (decision
    # D-02) removed the old max(50, …) communities-reached floor: the
    # figure is the true recorded sum everywhere it is used.
    from .metrics import headline_figures
    figures = headline_figures()
    verified_members = figures['verified_members']
    lgas_active = figures['lgas_active']
    wards_active = figures['wards_active']
    communities_reached = figures['communities_reached']
    context = {
        'featured_campaigns': featured_campaigns,
        'latest_news': latest_news,
        'latest_opportunities': latest_opportunities,
        'network_figures': {
            'verified_members': verified_members,
            'lgas_active': lgas_active,
            'wards_active': wards_active,
            'communities_reached': communities_reached,
        },
    }
    return render(request, 'core/home.html', context)

def about(request):
    return render(request, 'core/about.html', {
        'crumbs': [('About', None)],
    })

def patrons(request):
    from .models import Patron
    grand_patron = Patron.objects.filter(patron_type='GRAND', is_published=True).first()
    patrons_list = Patron.objects.filter(patron_type='PATRON', is_published=True)

    context = {
        'grand_patron': grand_patron,
        'patrons': patrons_list,
        'crumbs': [('Our Patrons', None)],
    }
    return render(request, 'core/patrons.html', context)

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
                status='VERIFIED',
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
                status='VERIFIED',
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
                status='VERIFIED',
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
                status='VERIFIED',
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
                    status='VERIFIED',
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
                    status='VERIFIED',
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
                    status='VERIFIED',
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
                    status='VERIFIED',
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
        'crumbs': [('Leadership', None)],
    }
    return render(request, 'core/leadership.html', context)

def view_profile(request, user_id):
    profile_user = get_object_or_404(User, id=user_id, status='VERIFIED', is_superuser=False)
    from django.urls import reverse

    context = {
        'profile_user': profile_user,
        'crumbs': [
            ('Leadership', reverse('core:leadership')),
            (profile_user.get_full_name(), None),
        ],
    }
    return render(request, 'core/view_profile.html', context)

def impact(request):
    """Impact & Metrics (brief §H; Page-by-Page Upgrade Priority 5).

    Every figure is computed from the records it counts:
    ``core.metrics`` builds the six measurement groups with each
    metric's definition, reporting period, last-updated date and
    source, and ``core.coverage`` builds the public Kebbi coverage
    map. Decision D-02 removed the old max(50, …) floor from
    communities_reached — it is the true recorded sum. Decision D-14:
    no financial figures are published.
    """
    from .coverage import coverage_rows, coverage_totals
    from .metrics import headline_figures, metric_groups
    from .models import CommunityReport, ImpactStory

    figures = headline_figures()
    rows = coverage_rows()
    totals = coverage_totals(rows)

    selected = None
    selected_pk = None
    lga_param = request.GET.get('lga', '')
    if lga_param:
        try:
            selected_pk = int(lga_param)
        except (TypeError, ValueError):
            selected_pk = None
    if selected_pk is not None:
        for row in rows:
            if row['lga'].pk == selected_pk:
                selected = row
                break

    from intelligence.map_data import VIEWBOX as map_viewbox

    context = {
        # Legacy headline keys (kept for any existing consumer).
        'verified_members': figures['verified_members'],
        'lgas_active': figures['lgas_active'],
        'wards_active': figures['wards_active'],
        'communities_reached': figures['communities_reached'],
        'trusted_reporters': User.objects.filter(
            is_trusted_reporter=True).count(),
        'reports_submitted': CommunityReport.objects.count(),
        'reports_verified': CommunityReport.objects.filter(
            status='APPROVED').count(),
        'opportunities_shared': Opportunity.objects.count(),
        'impact_stories': ImpactStory.objects.filter(
            is_published=True).order_by('-date_achieved'),
        # Priority 5: metric registry + public coverage map.
        'metric_groups': metric_groups(),
        'coverage_rows': rows,
        'coverage_totals': totals,
        'coverage_selected': selected,
        'selected_pk': selected['lga'].pk if selected else None,
        'map_viewbox': map_viewbox,
        'crumbs': [
            ('Impact & Metrics', None),
        ],
    }
    return render(request, 'core/impact.html', context)

def opportunities(request):
    """Opportunities Hub (brief §B). Public listings are OPEN,
    CLOSING_SOON and VERIFICATION_PENDING (public-with-badge, D-06);
    CLOSED listings live in the expired archive. Server-side search,
    category, status and location filters."""
    category = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    lga_id = request.GET.get('lga', '')
    search = request.GET.get('q', '').strip()

    base = Opportunity.objects.filter(
        status__in=['OPEN', 'CLOSING_SOON', 'VERIFICATION_PENDING']
    )

    filtered = base
    if category:
        filtered = filtered.filter(category=category)
    if status_filter in ('OPEN', 'CLOSING_SOON', 'VERIFICATION_PENDING'):
        filtered = filtered.filter(status=status_filter)
    if lga_id:
        filtered = filtered.filter(lga_id=lga_id)
    if search:
        filtered = filtered.filter(
            Q(title__icontains=search) | Q(provider__icontains=search) |
            Q(description__icontains=search)
        )

    has_filters = bool(category or status_filter or lga_id or search)
    if has_filters:
        featured_opps = []
        regular_qs = filtered.order_by('-created_at')
    else:
        featured_opps = list(base.filter(is_featured=True).order_by('-created_at')[:3])
        regular_qs = base.exclude(
            id__in=[f.id for f in featured_opps]).order_by('-created_at')

    # Paginate the listing grid (12 per page). The hub previously
    # rendered every live listing on a single page, so the page grew
    # without bound as listings accumulated (58 live listings measured
    # ~23,400px tall on a phone — the footer navigation sat ~28
    # screens down and the page felt endless). Page links preserve the
    # active filters, following the Story Archive pattern.
    page_obj = Paginator(regular_qs, 12).get_page(request.GET.get('page'))
    regular_opps = page_obj
    query_params = request.GET.copy()
    query_params.pop('page', None)
    opp_base_qs = query_params.urlencode()

    context = {
        'featured_opps': featured_opps,
        'regular_opps': regular_opps,
        'page_obj': page_obj,
        'opp_base_qs': opp_base_qs,
        'categories': Opportunity.CATEGORY_CHOICES,
        'status_choices': [c for c in Opportunity.STATUS_CHOICES if c[0] != 'CLOSED'],
        'lgas': LGA.objects.all().order_by('name'),
        'active_category': category,
        'active_status': status_filter,
        'active_lga': lga_id,
        'search_query': search,
        'has_filters': has_filters,
        'pending_count': base.filter(status='VERIFICATION_PENDING').count(),
        'open_count': base.filter(status__in=['OPEN', 'CLOSING_SOON']).count(),
    }
    return render(request, 'core/opportunities.html', context)


def opportunity_detail(request, slug):
    """Public detail page for one opportunity (brief §B). A listing
    still being verified shows no application link (D-06)."""
    opp = get_object_or_404(Opportunity, slug=slug)
    related = Opportunity.objects.filter(
        category=opp.category,
        status__in=['OPEN', 'CLOSING_SOON', 'VERIFICATION_PENDING'],
    ).exclude(pk=opp.pk).order_by('-created_at')[:3]
    days_left = None
    if opp.deadline:
        days_left = (opp.deadline - timezone.localdate()).days
    from django.urls import reverse
    crumbs = [
        ('Opportunities', reverse('core:opportunities')),
        (opp.title if len(opp.title) <= 60 else opp.title[:57] + '…', None),
    ]
    context = {
        'opp': opp,
        'related': related,
        'days_left': days_left,
        'application_link': opp.public_application_link,
        'crumbs': crumbs,
    }
    return render(request, 'core/opportunity_detail.html', context)


def opportunities_archive(request):
    """Expired-opportunities archive (brief §B): CLOSED listings stay
    publicly visible here so a closed listing can still be checked."""
    closed = Opportunity.objects.filter(status='CLOSED').order_by(
        F('deadline').desc(nulls_last=True), '-created_at')
    category = request.GET.get('category', '')
    if category:
        closed = closed.filter(category=category)
    # Same pagination as the hub (12 per page): the expired archive
    # previously rendered every closed listing on one page, which
    # grows without bound as listings close.
    page_obj = Paginator(closed, 12).get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    from django.urls import reverse
    context = {
        'closed_opps': page_obj,
        'page_obj': page_obj,
        'opp_base_qs': query_params.urlencode(),
        'categories': Opportunity.CATEGORY_CHOICES,
        'active_category': category,
        'crumbs': [
            ('Opportunities', reverse('core:opportunities')),
            ('Expired opportunities archive', None),
        ],
    }
    return render(request, 'core/opportunities_archive.html', context)


from django_ratelimit.decorators import ratelimit


@ratelimit(key='ip', rate='5/h', method='POST', block=True)
def report_opportunity(request, slug):
    """Report a suspicious listing (brief §B, D-07). No account needed.
    The report goes to the staff triage queue in Manage Opportunities;
    nothing is published or changed automatically."""
    from .forms import OpportunityReportForm
    opp = get_object_or_404(Opportunity, slug=slug)
    if request.method == 'POST':
        form = OpportunityReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.opportunity = opp
            report.save()
            messages.success(
                request,
                'Thank you. Your report has been received and will be reviewed by the KPN team.')
            return redirect('core:opportunity_detail', slug=opp.slug)
    else:
        form = OpportunityReportForm()
    from django.urls import reverse
    crumbs = [
        ('Opportunities', reverse('core:opportunities')),
        (opp.title if len(opp.title) <= 60 else opp.title[:57] + '…',
         reverse('core:opportunity_detail', kwargs={'slug': opp.slug})),
        ('Report this listing', None),
    ]
    return render(request, 'core/report_opportunity.html',
                  {'opp': opp, 'form': form, 'crumbs': crumbs})

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
        'crumbs': [('Gallery', None)],
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
                recipient_list=[settings.CONTACT_RECIPIENT_EMAIL],
                fail_silently=False,
            )
            
            messages.success(request, 'Thank you for contacting us! We will get back to you soon.')
        except Exception as e:
            messages.error(request, 'There was an error sending your message. Please try again later or contact us directly via email.')
        
        return redirect('core:contact')

    return render(request, 'core/contact.html', {
        'crumbs': [('Contact', None)],
    })

def support_us(request):
    return render(request, 'core/support_us.html', {
        'crumbs': [('Support KPN', None)],
    })

def faq(request):
    faqs = FAQ.objects.filter(is_active=True)
    context = {
        'faqs': faqs,
        'crumbs': [('FAQ', None)],
    }
    return render(request, 'core/faq.html', context)

def code_of_conduct(request):
    return render(request, 'core/code_of_conduct.html', {
        'crumbs': [('Code of Conduct', None)],
    })


@login_required
@approved_leader_required
def submit_report(request):
    from core.services.reports import recipient_for,create_report,report_type_for,ReportWorkflowError
    user=request.user
    FormClass={'WARD':WardReportForm,'LGA':LGAReportForm,'ZONAL':ZonalReportForm}.get(user.role)
    if not FormClass:
        messages.error(request,'Report submission is only available for Ward, LGA, and Zonal leaders.')
        return redirect('staff:dashboard')
    try: submitted_to=recipient_for(user)
    except ReportWorkflowError as exc:
        messages.error(request,exc.message); return redirect('staff:dashboard')
    if not submitted_to:
        messages.error(request,'No supervisor found to submit the report to. Please contact the administrator.')
        return redirect('staff:dashboard')
    if request.method=='POST':
        form=FormClass(request.POST)
        if form.is_valid():
            try: report=create_report(user,**form.cleaned_data)
            except ReportWorkflowError as exc:
                messages.error(request,exc.message)
            else:
                messages.success(request,f'Report submitted successfully to {submitted_to.get_full_name()}!')
                return redirect('staff:dashboard')
    else: form=FormClass()
    return render(request,'core/submit_report.html',{'form':form,'report_type':report_type_for(user),'submitted_to':submitted_to})

@login_required
@approved_leader_required
def review_report(request,report_id):
    from core.services.reports import reports_for,review_report as decide_report,ReportWorkflowError
    report=get_object_or_404(reports_for(request.user),id=report_id)
    if request.method=='POST':
        form=ReportReviewForm(request.POST,instance=report)
        if form.is_valid():
            action=request.POST.get('action')
            try: decided,child=decide_report(request.user,report.id,action,form.cleaned_data.get('review_notes',''))
            except ReportWorkflowError as exc: messages.error(request,exc.message)
            else:
                if child: messages.success(request,f'Report approved and escalated to {child.submitted_to.get_full_name()}!')
                elif action=='APPROVED' and decided.can_be_escalated(): messages.warning(request,'Report approved but could not be escalated - no supervisor found for the next level. Please contact the administrator to ensure all coordinator positions are filled.')
                else: messages.success(request,f'Report has been {dict(APPROVED="approved",FLAGGED="flagged for issues",REJECTED="rejected").get(action,"reviewed")} successfully!')
                return redirect('staff:dashboard')
    else: form=ReportReviewForm(instance=report)
    return render(request,'core/review_report.html',{'report':report,'form':form})

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
            role_definition__title='Senatorial Director',
            status='VERIFIED'
        ).first()
    elif original_report.report_type == 'LGA_TO_ZONAL':
        next_report_type = 'ZONAL_TO_STATE'
        next_supervisor = User.objects.filter(
            role='STATE',
            role_definition__title='Director of Monitoring & Compliance',
            status='VERIFIED'
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
    """Send email and in-app notification for report submission or review"""
    from core.notifications import notify
    try:
        if notification_type == 'submitted':
            if report.submitted_to:
                # In-app notification
                notify(
                    report.submitted_to,
                    notif_type='INFO',
                    title='New Report Submitted',
                    message=f"{report.submitted_by.get_full_name()} submitted a {report.get_report_type_display()}.",
                    link=f'/review-report/{report.id}/'
                )
                
                # Email notification
                if report.submitted_to.email:
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
            if report.submitted_by:
                status_text = report.get_status_display()
                
                # In-app notification
                notif_type_map = {'APPROVED': 'SUCCESS', 'REJECTED': 'ACTION', 'FLAGGED': 'WARNING'}
                n_type = notif_type_map.get(report.status, 'INFO')
                notify(
                    report.submitted_by,
                    notif_type=n_type,
                    title=f'Report {status_text}',
                    message=f"Your report '{report.title}' was reviewed by {report.reviewed_by.get_full_name() if report.reviewed_by else 'a supervisor'}.",
                    link='#'
                )
                
                # Email notification
                if report.submitted_by.email:
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

from .models import CommunityInitiative, AdvocacyCampaign, CommunityReport
from .forms import CommunityReportForm

# ──────────────────────────────────────────────────────────────────────
# COMMUNITY HUB (Page-by-Page Upgrade Priority 2, brief §D)
# ──────────────────────────────────────────────────────────────────────

def community(request):
    """Community Hub. Initiatives are shown with their real lifecycle
    state — a planned initiative is never presented as active — and
    can be filtered by status, type and LGA."""
    status_filter = request.GET.get('status', '')
    category = request.GET.get('category', '')
    lga_id = request.GET.get('lga', '')
    search = request.GET.get('q', '').strip()

    base = CommunityInitiative.objects.select_related('lga', 'ward')
    filtered = base
    if status_filter in dict(CommunityInitiative.STATUS_CHOICES):
        filtered = filtered.filter(status=status_filter)
    if category in dict(CommunityInitiative.CATEGORY_CHOICES):
        filtered = filtered.filter(category=category)
    if lga_id:
        filtered = filtered.filter(lga_id=lga_id)
    if search:
        filtered = filtered.filter(
            Q(title__icontains=search) | Q(description__icontains=search) |
            Q(location_text__icontains=search))

    has_filters = bool(status_filter or category or lga_id or search)
    today = timezone.localdate()
    all_initiatives = list(base)
    context = {
        'initiatives': filtered,
        'has_filters': has_filters,
        'categories': CommunityInitiative.CATEGORY_CHOICES,
        'status_choices': [
            (value, CommunityInitiative.PUBLIC_STATUS_LABELS.get(value, label))
            for value, label in CommunityInitiative.STATUS_CHOICES
        ],
        'status_labels': CommunityInitiative.PUBLIC_STATUS_LABELS,
        'lgas': LGA.objects.all().order_by('name'),
        'active_status': status_filter,
        'active_category': category,
        'active_lga': lga_id,
        'search_query': search,
        'active_count': sum(1 for i in all_initiatives if i.status == 'ACTIVE'),
        'completed_count': sum(1 for i in all_initiatives if i.status == 'COMPLETED'),
        # Grouped lifecycle sections for the unfiltered hub. A planned
        # initiative is never presented as active (brief §D).
        'active_list': [i for i in all_initiatives if i.status == 'ACTIVE'],
        'completed_list': [i for i in all_initiatives if i.status == 'COMPLETED'],
        'other_list': [i for i in all_initiatives
                       if i.status not in ('ACTIVE', 'COMPLETED')],
        # Upcoming outreach = planned initiatives with a real future
        # start date. Only records that exist are shown.
        'upcoming': [] if has_filters else [
            i for i in all_initiatives
            if i.status == 'PLANNING' and i.start_date and i.start_date >= today
        ][:3],
        'volunteer_opps': [] if has_filters else list(
            Opportunity.objects.filter(
                category='VOLUNTEER',
                status__in=['OPEN', 'CLOSING_SOON', 'VERIFICATION_PENDING'],
            ).order_by('-created_at')[:3]),
        'voice_count': CommunityReport.objects.filter(
            published_to_voice=True).count(),
    }
    return render(request, 'core/community.html', context)


def community_initiative_detail(request, pk):
    initiative = get_object_or_404(
        CommunityInitiative.objects.select_related('lga', 'ward'), pk=pk)
    from django.urls import reverse
    related = CommunityInitiative.objects.filter(
        lga=initiative.lga).exclude(pk=initiative.pk)[:3] if initiative.lga else []
    crumbs = [
        ('Community', reverse('core:community')),
        (initiative.title if len(initiative.title) <= 60
         else initiative.title[:57] + '…', None),
    ]
    return render(request, 'core/community_initiative_detail.html', {
        'initiative': initiative, 'related': related, 'crumbs': crumbs})


@ratelimit(key='ip', rate='5/h', method='POST', block=True)
def community_report(request):
    """Public community-report route (brief §D/§E, decision D-08).

    Open to anyone, but controlled: the submission lands in the same
    CommunityReport PENDING review queue as trusted-reporter reports.
    Nothing is published automatically — Community Voice shows only
    reports a reviewer explicitly publishes."""
    from .forms import PublicCommunityReportForm
    if request.method == 'POST':
        form = PublicCommunityReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.status = 'PENDING'
            report.save()
            return redirect('core:community_report_submitted')
    else:
        form = PublicCommunityReportForm()
    from django.urls import reverse
    crumbs = [
        ('Community', reverse('core:community')),
        ('Report a community concern', None),
    ]
    return render(request, 'core/community_report_form.html',
                  {'form': form, 'crumbs': crumbs})


def community_report_submitted(request):
    from django.urls import reverse
    crumbs = [
        ('Community', reverse('core:community')),
        ('Report a community concern', reverse('core:community_report')),
        ('Received', None),
    ]
    return render(request, 'core/community_report_submitted.html',
                  {'crumbs': crumbs})


# ──────────────────────────────────────────────────────────────────────
# CIVIC ENGAGEMENT & ADVOCACY (Priority 2, brief §2 + §E)
# One section, five subsections. /civic/ is the section landing and
# /advocacy/ keeps the campaigns; both routes survive the merger
# (decision D-11 — the merger is navigational).
# ──────────────────────────────────────────────────────────────────────

def _civic_counts():
    from story_intelligence.models import Promise
    from intelligence.models import Project
    return {
        'promise_count': Promise.objects.count(),
        'project_count': Project.objects.count(),
        'voice_count': CommunityReport.objects.filter(
            published_to_voice=True).count(),
        'campaign_count': AdvocacyCampaign.objects.filter(
            is_active=True, status__in=['ACTIVE', 'PAUSED']).count(),
    }


def civic(request):
    """Civic Engagement & Advocacy — section landing."""
    return render(request, 'core/civic.html', _civic_counts())


def civic_education(request):
    from django.urls import reverse
    crumbs = [
        ('Civic Engagement & Advocacy', reverse('core:civic')),
        ('Civic Education', None),
    ]
    return render(request, 'core/civic_education.html', {'crumbs': crumbs})


def civic_governance(request):
    """Governance & Accountability — framing and live links into the
    existing trackers and archive. No new records are created here."""
    from django.urls import reverse
    from story_intelligence.models import Promise
    from intelligence.models import Project
    context = _civic_counts()
    context.update({
        'recent_promises': list(
            Promise.objects.order_by('-created_at')[:3]),
        'recent_projects': list(
            Project.objects.order_by('-created_at')[:3]),
        'crumbs': [
            ('Civic Engagement & Advocacy', reverse('core:civic')),
            ('Governance & Accountability', None),
        ],
    })
    return render(request, 'core/civic_governance.html', context)


def community_voice(request):
    """Community Voice — documented concerns a reviewer has explicitly
    published (D-08). Reporter names and phone numbers are never
    shown publicly; concerns are attributed to their community and
    carry their verification level."""
    from django.urls import reverse
    concerns = (CommunityReport.objects
                .filter(published_to_voice=True)
                .select_related('lga', 'ward', 'escalated_campaign')
                .order_by('-voice_published_at', '-created_at'))
    crumbs = [
        ('Civic Engagement & Advocacy', reverse('core:civic')),
        ('Community Voice', None),
    ]
    return render(request, 'core/community_voice.html',
                  {'concerns': concerns, 'crumbs': crumbs})


def advocacy(request):
    """Advocacy Campaigns — the campaigns subsection. Current and
    concluded campaigns are listed separately so a finished campaign
    is never presented as ongoing."""
    all_campaigns = (AdvocacyCampaign.objects.filter(is_active=True)
                     .prefetch_related('activities'))
    current = [c for c in all_campaigns if c.status in ('ACTIVE', 'PAUSED')]
    concluded = [c for c in all_campaigns if c.status in ('COMPLETED', 'CLOSED')]
    from django.urls import reverse
    crumbs = [
        ('Civic Engagement & Advocacy', reverse('core:civic')),
        ('Advocacy Campaigns', None),
    ]
    return render(request, 'core/advocacy.html', {
        'advocacy_campaigns': all_campaigns,
        'current_campaigns': current,
        'concluded_campaigns': concluded,
        'crumbs': crumbs,
    })


def advocacy_detail(request, pk):
    """One campaign, full structure (brief §E): objective, background
    and problem, evidence, affected communities, proposed action,
    KPN's position, progress and activities, government response and
    final outcome where concluded."""
    campaign = get_object_or_404(
        AdvocacyCampaign.objects.prefetch_related('activities', 'evidence_articles'),
        pk=pk, is_active=True)
    from django.urls import reverse
    evidence = [a for a in campaign.evidence_articles.all()
                if a.status == 'PUBLISHED']
    crumbs = [
        ('Civic Engagement & Advocacy', reverse('core:civic')),
        ('Advocacy Campaigns', reverse('core:advocacy')),
        (campaign.title if len(campaign.title) <= 60
         else campaign.title[:57] + '…', None),
    ]
    return render(request, 'core/advocacy_detail.html', {
        'campaign': campaign,
        'activities': campaign.activities.all(),
        'evidence_articles': evidence,
        'crumbs': crumbs,
    })


def election_observation(request):
    """Election Observation (decision D-12): education, participation
    and reporting guidance, plus published findings — linked from
    real published records only. A records system is built when KPN
    runs an observation mission, not before."""
    from django.urls import reverse
    from campaigns.models import Campaign as Article
    findings = (Article.objects.filter(status='PUBLISHED')
                .filter(Q(title__icontains='election') |
                        Q(title__icontains='observer') |
                        Q(title__icontains='polling'))
                .order_by('-published_at')[:6])
    crumbs = [
        ('Civic Engagement & Advocacy', reverse('core:civic')),
        ('Election Observation', None),
    ]
    return render(request, 'core/election_observation.html',
                  {'findings': findings, 'crumbs': crumbs})

from django.contrib.auth.decorators import login_required

@login_required(login_url='staff:login')
def report_a_story(request):
    if request.user.status != 'VERIFIED':
        messages.error(request, 'Only verified KPN members can access this feature.')
        return redirect('core:home')
    
    # Only Trusted Reporters and Leaders can submit official community reports
    can_report = request.user.is_trusted_reporter or request.user.is_leader()
    if not can_report:
        messages.warning(
            request,
            'Only KPN Trusted Reporters and Leaders can submit community reports. '
            'Build your reporting record first and your LGA or Senatorial Team can recommend you for Trusted Reporter status.'
        )
        return redirect('core:home')
        
    if request.method == 'POST':
        form = CommunityReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save()
            messages.success(request, 'Your story has been submitted successfully and is pending review. Thank you!')
            return redirect('core:home')
    else:
        initial_data = {
            'reporter_name': request.user.get_full_name() or request.user.username,
            'reporter_phone': getattr(request.user, 'phone', ''),
            'zone': getattr(request.user, 'zone', None),
            'lga': getattr(request.user, 'lga', None),
            'ward': getattr(request.user, 'ward', None),
        }
        form = CommunityReportForm(initial=initial_data)
    
    return render(request, 'core/report_a_story.html', {'form': form})

# ──────────────────────────────────────────────────────────────────────────────
# NETWORK RANKINGS
# ──────────────────────────────────────────────────────────────────────────────

def network_rankings(request):
    from django.db.models import Count, Q
    from staff.models import User
    from leadership.models import LGA, Ward
    from core.models import CommunityReport
    
    # PUBLIC RANKINGS (Positive only)
    # Top Active LGAs (by verified members)
    top_lgas = LGA.objects.annotate(
        active_members=Count('members', filter=Q(members__status='VERIFIED'))
    ).filter(active_members__gt=0).order_by('-active_members')[:5]
    
    # Top Active Wards
    top_wards = Ward.objects.annotate(
        active_members=Count('members', filter=Q(members__status='VERIFIED'))
    ).filter(active_members__gt=0).order_by('-active_members')[:5]
    
    # Top Community Reporters (by approved reports)
    # We don't have a direct FK from report to user, only reporter_name.
    # So we'll just show Trusted Reporters as the top list for now.
    trusted_reporters = User.objects.filter(status='VERIFIED', is_trusted_reporter=True)
    
    # INTERNAL RANKINGS (Only for leaders)
    internal_data = None
    if request.user.is_authenticated and request.user.is_leader():
        # Find LGAs with ZERO verified members
        inactive_lgas = LGA.objects.annotate(
            active_members=Count('members', filter=Q(members__status='VERIFIED'))
        ).filter(active_members=0).order_by('name')
        
        # Pending community reports count
        pending_reports = CommunityReport.objects.filter(status='PENDING').count()
        
        internal_data = {
            'inactive_lgas': inactive_lgas,
            'pending_reports': pending_reports,
        }
        
    context = {
        'top_lgas': top_lgas,
        'top_wards': top_wards,
        'trusted_reporters': trusted_reporters,
        'internal_data': internal_data,
        'crumbs': [('Network Rankings', None)],
    }
    
    return render(request, 'core/network_rankings.html', context)


# ── App Download ─────────────────────────────────────────────────────

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import FileResponse, Http404
from django.template.defaultfilters import filesizeformat

APP_APK_PATH = 'app/kpn-app.apk'
APP_VERSION_PATH = 'app/VERSION.txt'


def _app_download_info():
    """What the Download App page can truthfully offer right now.

    Reads the APK slot (static/app/) through the staticfiles storage:
    the download is only offered when the signed release APK is
    actually there, and the size/version shown are the file's own,
    never invented.
    """
    info = {'available': False, 'size': None, 'version': None}
    if staticfiles_storage.exists(APP_APK_PATH):
        info['available'] = True
        info['size'] = filesizeformat(staticfiles_storage.size(APP_APK_PATH))
        if staticfiles_storage.exists(APP_VERSION_PATH):
            with staticfiles_storage.open(APP_VERSION_PATH, 'rb') as fh:
                version = fh.read().decode('utf-8', 'ignore').strip()
            info['version'] = version or None
    return info


def download_app(request):
    context = _app_download_info()
    context['crumbs'] = [('Download the App', None)]
    return render(request, 'core/download_app.html', context)


def download_app_apk(request):
    if not staticfiles_storage.exists(APP_APK_PATH):
        raise Http404('The KPN app file has not been added yet.')
    return FileResponse(
        staticfiles_storage.open(APP_APK_PATH, 'rb'),
        as_attachment=True,
        filename='kpn-app.apk',
        content_type='application/vnd.android.package-archive',
    )


# ── Notification Views ────────────────────────────────────────────────

@login_required
def mark_notifications_read(request):
    """Mark all of the logged-in user's notifications as read and redirect back."""
    from .notification_queries import visible_notifications
    from django.utils.http import url_has_allowed_host_and_scheme
    visible_notifications(request.user).filter(is_read=False).update(is_read=True)
    next_url = request.POST.get('next') or request.GET.get('next', '/')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = '/'
    return redirect(next_url)
