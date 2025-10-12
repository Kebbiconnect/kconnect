from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Campaign
from .forms import CampaignForm
from staff.decorators import approved_leader_required, specific_role_required


@approved_leader_required
def create_campaign(request):
    """Create a new campaign"""
    if request.method == 'POST':
        form = CampaignForm(request.POST, request.FILES)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.author = request.user
            campaign.status = 'DRAFT'
            campaign.save()
            messages.success(request, 'Campaign created successfully!')
            return redirect('campaigns:my_campaigns')
    else:
        form = CampaignForm()
    
    context = {
        'form': form,
    }
    return render(request, 'campaigns/create_campaign.html', context)


@approved_leader_required
def my_campaigns(request):
    """List all campaigns created by the current user"""
    campaigns = Campaign.objects.filter(author=request.user).order_by('-created_at')
    
    context = {
        'campaigns': campaigns,
    }
    return render(request, 'campaigns/my_campaigns.html', context)


@approved_leader_required
def edit_campaign(request, campaign_id):
    """Edit an existing campaign"""
    campaign = get_object_or_404(Campaign, pk=campaign_id, author=request.user)
    
    if campaign.status == 'PUBLISHED':
        messages.error(request, 'Cannot edit a published campaign.')
        return redirect('campaigns:my_campaigns')
    
    if request.method == 'POST':
        form = CampaignForm(request.POST, request.FILES, instance=campaign)
        if form.is_valid():
            form.save()
            messages.success(request, 'Campaign updated successfully!')
            return redirect('campaigns:my_campaigns')
    else:
        form = CampaignForm(instance=campaign)
    
    context = {
        'form': form,
        'campaign': campaign,
    }
    return render(request, 'campaigns/edit_campaign.html', context)


@approved_leader_required
def delete_campaign(request, campaign_id):
    """Delete a campaign"""
    campaign = get_object_or_404(Campaign, pk=campaign_id, author=request.user)
    
    if campaign.status == 'PUBLISHED':
        messages.error(request, 'Cannot delete a published campaign.')
        return redirect('campaigns:my_campaigns')
    
    if request.method == 'POST':
        campaign.delete()
        messages.success(request, 'Campaign deleted successfully!')
        return redirect('campaigns:my_campaigns')
    
    context = {
        'campaign': campaign,
    }
    return render(request, 'campaigns/delete_campaign.html', context)


@approved_leader_required
def submit_for_approval(request, campaign_id):
    """Submit a campaign for approval"""
    campaign = get_object_or_404(Campaign, pk=campaign_id, author=request.user)
    
    if campaign.status != 'DRAFT':
        messages.error(request, 'Only draft campaigns can be submitted for approval.')
        return redirect('campaigns:my_campaigns')
    
    if request.method == 'POST':
        campaign.status = 'PENDING'
        campaign.save()
        messages.success(request, 'Campaign submitted for approval!')
        return redirect('campaigns:my_campaigns')
    
    context = {
        'campaign': campaign,
    }
    return render(request, 'campaigns/submit_for_approval.html', context)


@specific_role_required('Director of Media & Publicity')
def approval_queue(request):
    """View all campaigns pending approval (Director only)"""
    pending_campaigns = Campaign.objects.filter(status='PENDING').order_by('-created_at')
    
    context = {
        'pending_campaigns': pending_campaigns,
    }
    return render(request, 'campaigns/approval_queue.html', context)


@specific_role_required('Director of Media & Publicity')
def approve_campaign(request, campaign_id):
    """Approve a campaign and publish it"""
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    
    if campaign.status != 'PENDING':
        messages.error(request, 'Only pending campaigns can be approved.')
        return redirect('campaigns:approval_queue')
    
    if request.method == 'POST':
        campaign.status = 'PUBLISHED'
        campaign.approved_by = request.user
        campaign.published_at = timezone.now()
        campaign.save()
        messages.success(request, f'Campaign "{campaign.title}" has been approved and published!')
        return redirect('campaigns:approval_queue')
    
    context = {
        'campaign': campaign,
    }
    return render(request, 'campaigns/approve_campaign.html', context)


@specific_role_required('Director of Media & Publicity')
def reject_campaign(request, campaign_id):
    """Reject a campaign"""
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    
    if campaign.status != 'PENDING':
        messages.error(request, 'Only pending campaigns can be rejected.')
        return redirect('campaigns:approval_queue')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        campaign.status = 'REJECTED'
        campaign.save()
        messages.success(request, f'Campaign "{campaign.title}" has been rejected.')
        return redirect('campaigns:approval_queue')
    
    context = {
        'campaign': campaign,
    }
    return render(request, 'campaigns/reject_campaign.html', context)


@login_required
def view_campaign(request, slug):
    """Public view for a published campaign"""
    campaign = get_object_or_404(Campaign, slug=slug, status='PUBLISHED')
    
    campaign.views += 1
    campaign.save(update_fields=['views'])
    
    context = {
        'campaign': campaign,
    }
    return render(request, 'campaigns/view_campaign.html', context)


@login_required
def all_campaigns(request):
    """List all published campaigns"""
    campaigns = Campaign.objects.filter(status='PUBLISHED').order_by('-published_at')
    
    context = {
        'campaigns': campaigns,
    }
    return render(request, 'campaigns/all_campaigns.html', context)
