"""
campaigns/views.py — KPN Newsroom views.

Public:
  newsroom          /campaigns/
  article_detail    /campaigns/<slug>/
  
Staff (writers - any approved leader):
  write_article     /campaigns/write/
  my_articles       /campaigns/my-articles/
  edit_article      /campaigns/edit/<id>/
  delete_article    /campaigns/delete/<id>/
  submit_for_review /campaigns/submit/<id>/
  image_upload      /campaigns/api/upload-image/  (Editor.js image tool)

Editors (Director of Media & Communications):
  review_queue      /campaigns/review/
  publish_article   /campaigns/publish/<id>/
  return_article    /campaigns/return/<id>/
"""
import json
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Q

from .models import Campaign
from .forms import ArticleForm, CampaignForm
from staff.decorators import approved_leader_required, specific_role_required
from leadership.models import LGA, Ward

# Roles permitted to review and publish articles
EDITOR_ROLES = [
    'Director of Media & Communications',
    'Assistant Director of Media & Communications',
    'President',
    'General Secretary',
]


# ─── PUBLIC VIEWS ──────────────────────────────────────────────────────────────

def newsroom(request):
    """Public newsroom listing — filterable by category and LGA."""
    articles = Campaign.objects.filter(status='PUBLISHED').select_related(
        'author', 'lga', 'ward', 'approved_by'
    ).order_by('-published_at')

    category = request.GET.get('category', '')
    lga_id = request.GET.get('lga', '')
    verification = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

    if category:
        articles = articles.filter(category=category)
    if lga_id:
        articles = articles.filter(lga_id=lga_id)
    if verification:
        articles = articles.filter(verification_status=verification)
    if search:
        articles = articles.filter(
            Q(title__icontains=search) |
            Q(subheadline__icontains=search) |
            Q(location__icontains=search)
        )

    featured = articles.first()
    rest = articles[1:13] if featured else articles[:12]

    lgas = LGA.objects.all().order_by('name')

    context = {
        'articles': articles,
        'featured': featured,
        'rest': rest,
        'lgas': lgas,
        'categories': Campaign.CATEGORY_CHOICES,
        'verification_choices': Campaign.VERIFICATION_STATUS_CHOICES,
        'active_category': category,
        'active_lga': lga_id,
        'active_verification': verification,
        'search_query': search,
    }
    return render(request, 'campaigns/newsroom.html', context)


def article_detail(request, slug):
    """Public article detail page."""
    article = get_object_or_404(Campaign, slug=slug)

    # Security check: only show if published, OR if the current user is the author or a media director
    if article.status != 'PUBLISHED':
        is_author = request.user.is_authenticated and article.author == request.user
        is_editor = request.user.is_authenticated and request.user.is_leader()
        if not (is_author or is_editor):
            from django.http import Http404
            raise Http404("No published Campaign matches the given query.")

    # Increment view count (lightweight, non-atomic is fine here) - only if published to not inflate counts during preview
    if article.status == 'PUBLISHED':
        Campaign.objects.filter(pk=article.pk).update(views=article.views + 1)
        article.views += 1

    # Related articles — same category, exclude current
    related = Campaign.objects.filter(
        status='PUBLISHED', category=article.category
    ).exclude(pk=article.pk).order_by('-published_at')[:4]

    context = {
        'article': article,
        'related': related,
    }
    return render(request, 'campaigns/article_detail.html', context)


# ─── WRITER VIEWS (any approved leader) ────────────────────────────────────────

@approved_leader_required
def write_article(request):
    """CMS editor — create a new article."""
    if request.method == 'POST':
        form = ArticleForm(request.POST, request.FILES)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.status = 'DRAFT'
            article.save()
            messages.success(request, 'Article saved as draft.')
            return redirect('campaigns:my_articles')
        else:
            messages.error(request, 'Please check the form for errors.')
    else:
        form = ArticleForm()

    return render(request, 'campaigns/write_article.html', {
        'form': form,
        'mode': 'create',
        'existing_content_json': '',
    })


@approved_leader_required
def my_articles(request):
    """List articles authored by the current user."""
    articles = Campaign.objects.filter(author=request.user).order_by('-updated_at')
    context = {'articles': articles}
    return render(request, 'campaigns/my_articles.html', context)


@approved_leader_required
def edit_article(request, article_id):
    """CMS editor — edit an existing draft or rejected article."""
    article = get_object_or_404(Campaign, pk=article_id, author=request.user)

    if article.status == 'PUBLISHED':
        messages.error(request, 'Published articles cannot be edited. Contact the Media Director.')
        return redirect('campaigns:my_articles')

    if request.method == 'POST':
        form = ArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            updated = form.save(commit=False)
            # Reset status to DRAFT if it was REJECTED, so it goes back through review
            if updated.status == 'REJECTED':
                updated.status = 'DRAFT'
                updated.rejection_note = ''
            updated.save()
            messages.success(request, 'Article updated successfully.')
            return redirect('campaigns:my_articles')
        else:
            messages.error(request, 'Please check the form for errors.')
    else:
        form = ArticleForm(instance=article)

    # Pass existing Editor.js JSON as string for JavaScript to load
    existing_content_json = json.dumps(article.content_json) if article.content_json else ''

    return render(request, 'campaigns/write_article.html', {
        'form': form,
        'article': article,
        'existing_content_json': existing_content_json,
        'mode': 'edit',
    })


@approved_leader_required
def delete_article(request, article_id):
    """Delete a draft or rejected article."""
    article = get_object_or_404(Campaign, pk=article_id, author=request.user)

    if article.status in ['PUBLISHED', 'PENDING']:
        messages.error(request, 'Cannot delete a published or pending article.')
        return redirect('campaigns:my_articles')

    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Article deleted.')
        return redirect('campaigns:my_articles')

    return render(request, 'campaigns/delete_article.html', {'article': article})


@approved_leader_required
def submit_for_review(request, article_id):
    """Submit a draft article to the editorial review queue."""
    article = get_object_or_404(Campaign, pk=article_id, author=request.user)

    if article.status != 'DRAFT':
        messages.error(request, 'Only draft articles can be submitted for review.')
        return redirect('campaigns:my_articles')

    if not (article.content_json or article.content) or (isinstance(article.content, str) and article.content.strip() == '<p><br></p>'):
        messages.error(request, 'Article body is empty. Add content before submitting.')
        return redirect('campaigns:edit_article', article_id=article.pk)

    if request.method == 'POST':
        article.status = 'PENDING'
        article.save(update_fields=['status'])
        messages.success(request, 'Article submitted for editorial review.')
        return redirect('campaigns:my_articles')

    return render(request, 'campaigns/submit_for_review.html', {'article': article})


# ─── IMAGE UPLOAD ENDPOINT (Editor.js) ────────────────────────────────────────

@login_required
@require_POST
def image_upload(request):
    """
    Editor.js image upload endpoint.
    Expects multipart/form-data with 'image' field.
    Returns: {"success": 1, "file": {"url": "<cloudinary_url>"}}
    """
    if not request.user.is_leader():
        return JsonResponse({'success': 0, 'error': 'Permission denied.'}, status=403)

    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'success': 0, 'error': 'No image provided.'}, status=400)

    # 1. Validate File Size (Max 2MB for article body images)
    if image_file.size > 2 * 1024 * 1024:
        return JsonResponse({'success': 0, 'error': 'File size exceeds 2MB.'}, status=400)

    # 2. Validate File Extension
    import os
    ext = os.path.splitext(image_file.name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return JsonResponse({'success': 0, 'error': 'Invalid file extension.'}, status=400)

    # 3. Validate actual MIME type and Dimensions (do not trust client)
    try:
        from PIL import Image
        img = Image.open(image_file)
        img.verify()  # Verify it's actually an image
        
        # Check dimensions (optional limit, e.g., max 4000x4000)
        width, height = img.size
        if width > 4000 or height > 4000:
            return JsonResponse({'success': 0, 'error': 'Image dimensions too large. Max 4000x4000.'}, status=400)
            
        if img.format.lower() not in ['jpeg', 'png', 'gif', 'webp', 'jpg']:
            return JsonResponse({'success': 0, 'error': 'Invalid image format.'}, status=400)
    except Exception:
        return JsonResponse({'success': 0, 'error': 'Invalid or corrupted image file.'}, status=400)

    # Reset file pointer after PIL verification
    image_file.seek(0)

    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            image_file,
            folder='kpn_newsroom/',
            resource_type='image',
        )
        return JsonResponse({
            'success': 1,
            'file': {'url': result.get('secure_url', '')},
        })
    except Exception as exc:
        return JsonResponse({'success': 0, 'error': str(exc)}, status=500)


# ─── EDITOR / REVIEW VIEWS ─────────────────────────────────────────────────────

@login_required
def review_queue(request):
    """Editorial review queue — visible to Media Director roles."""
    if not request.user.is_leader() or request.user.status != 'VERIFIED':
        messages.error(request, 'Access denied.')
        return redirect('staff:dashboard')

    role_title = getattr(request.user.role_definition, 'title', '')
    if role_title not in EDITOR_ROLES:
        messages.error(request, 'Only editors can access the review queue.')
        return redirect('staff:dashboard')

    pending = Campaign.objects.filter(status='PENDING').select_related(
        'author', 'lga'
    ).order_by('-updated_at')

    context = {'pending': pending}
    return render(request, 'campaigns/review_queue.html', context)


@login_required
def publish_article(request, article_id):
    """Publish an article from the review queue."""
    article = get_object_or_404(Campaign, pk=article_id)
    role_title = getattr(request.user.role_definition, 'title', '')
    if role_title not in EDITOR_ROLES:
        messages.error(request, 'Permission denied.')
        return redirect('staff:dashboard')

    if article.status != 'PENDING':
        messages.error(request, 'Only pending articles can be published.')
        return redirect('campaigns:review_queue')

    if request.method == 'POST':
        article.status = 'PUBLISHED'
        article.approved_by = request.user
        article.published_at = timezone.now()
        article.rejection_note = ''
        article.save(update_fields=['status', 'approved_by', 'published_at', 'rejection_note'])
        messages.success(request, f'"{article.title}" is now published.')
        return redirect('campaigns:review_queue')

    return render(request, 'campaigns/publish_confirm.html', {'article': article})


@login_required
def return_article(request, article_id):
    """Return an article for revision with an editor note."""
    article = get_object_or_404(Campaign, pk=article_id)
    role_title = getattr(request.user.role_definition, 'title', '')
    if role_title not in EDITOR_ROLES:
        messages.error(request, 'Permission denied.')
        return redirect('staff:dashboard')

    if article.status != 'PENDING':
        messages.error(request, 'Only pending articles can be returned.')
        return redirect('campaigns:review_queue')

    if request.method == 'POST':
        note = request.POST.get('rejection_note', '').strip()
        article.status = 'REJECTED'
        article.rejection_note = note
        article.save(update_fields=['status', 'rejection_note'])
        messages.success(request, f'Article returned to {article.author.get_full_name()} for revision.')
        return redirect('campaigns:review_queue')

    return render(request, 'campaigns/return_article.html', {'article': article})


# ─── AJAX HELPER ──────────────────────────────────────────────────────────────

@login_required
def get_wards_for_lga(request):
    """AJAX: return ward list for a given LGA ID (used by write_article form)."""
    lga_id = request.GET.get('lga_id')
    try:
        wards = list(
            Ward.objects.filter(lga_id=lga_id).order_by('name').values('id', 'name')
        )
        return JsonResponse({'wards': wards})
    except Exception:
        return JsonResponse({'wards': []})


# ─── LEGACY ALIASES (keep old URL names working) ───────────────────────────────
create_campaign = write_article
my_campaigns = my_articles
edit_campaign = edit_article
delete_campaign = delete_article
submit_for_approval = submit_for_review
approval_queue = review_queue
approve_campaign = publish_article
reject_campaign = return_article
view_campaign = article_detail
all_campaigns = newsroom
