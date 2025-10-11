from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from campaigns.models import Campaign
from media.models import MediaItem
from staff.models import User
from leadership.models import Zone, LGA, Ward
from .models import FAQ

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
    
    leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL')
    
    if zone_filter:
        leaders = leaders.filter(zone_id=zone_filter)
    if lga_filter:
        leaders = leaders.filter(lga_id=lga_filter)
    if ward_filter:
        leaders = leaders.filter(ward_id=ward_filter)
    
    zones = Zone.objects.all()
    lgas = LGA.objects.all()
    wards = Ward.objects.all()
    
    context = {
        'leaders': leaders,
        'zones': zones,
        'lgas': lgas,
        'wards': wards,
        'selected_zone': zone_filter,
        'selected_lga': lga_filter,
        'selected_ward': ward_filter,
    }
    return render(request, 'core/leadership.html', context)

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
        
        messages.success(request, 'Thank you for contacting us! We will get back to you soon.')
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
