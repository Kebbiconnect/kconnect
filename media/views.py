from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import MediaItem
from .forms import MediaUploadForm, MediaItemEditForm
from staff.decorators import specific_role_required, approved_leader_required
import os


def publicity_officer_required(view_func):
    """Decorator to check if user is a publicity officer at any level"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('staff:login')
        
        if request.user.status != 'APPROVED':
            messages.error(request, 'Your account is not approved yet.')
            return redirect('core:home')
        
        publicity_roles = [
            'Director of Media & Publicity',
            'Assistant Director of Media & Publicity',
            'Zonal Publicity Officer',
            'Publicity Officer',
        ]
        
        if not request.user.role_definition or request.user.role_definition.title not in publicity_roles:
            messages.error(request, 'Only publicity officers can access this page.')
            return redirect('staff:dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper


@publicity_officer_required
def create_media(request):
    """Create media posts with multiple file uploads"""
    if request.method == 'POST':
        form = MediaUploadForm(request.POST, request.FILES)
        files = request.FILES.getlist('files')
        
        if form.is_valid() and files:
            caption = form.cleaned_data['caption']
            uploaded_count = 0
            
            is_director = request.user.role_definition and request.user.role_definition.title == 'Director of Media & Publicity'
            
            for file in files:
                # Determine media type based on file extension
                file_ext = os.path.splitext(file.name)[1].lower()
                image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
                video_exts = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
                
                if file_ext in image_exts:
                    media_type = 'PHOTO'
                elif file_ext in video_exts:
                    media_type = 'VIDEO'
                else:
                    continue  # Skip unsupported files
                
                # Create media item with role information
                # Auto-approve for Director, pending for others
                media_item = MediaItem.objects.create(
                    title=f"Media by {request.user.get_full_name()}",
                    description=caption,
                    media_type=media_type,
                    file=file,
                    uploaded_by=request.user,
                    status='APPROVED' if is_director else 'PENDING',
                    approved_by=request.user if is_director else None
                )
                uploaded_count += 1
            
            if uploaded_count > 0:
                if is_director:
                    messages.success(request, f'Successfully uploaded {uploaded_count} media file(s) to the gallery!')
                else:
                    messages.success(request, f'Successfully uploaded {uploaded_count} media file(s). They are pending approval by the Director of Media & Publicity.')
                return redirect('media:my_media')
            else:
                messages.error(request, 'No valid media files were uploaded.')
        else:
            if not files:
                messages.error(request, 'Please select at least one file to upload.')
    else:
        form = MediaUploadForm()
    
    return render(request, 'media/create_media.html', {'form': form})


@publicity_officer_required
def my_media(request):
    """List all media posts uploaded by the current user"""
    media_items = MediaItem.objects.filter(uploaded_by=request.user).order_by('-created_at')
    
    context = {
        'media_items': media_items,
    }
    return render(request, 'media/my_media.html', context)


@publicity_officer_required
def edit_media(request, pk):
    """Edit a media post"""
    media_item = get_object_or_404(MediaItem, pk=pk, uploaded_by=request.user)
    
    if request.method == 'POST':
        form = MediaItemEditForm(request.POST, instance=media_item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Media item updated successfully!')
            return redirect('media:my_media')
    else:
        form = MediaItemEditForm(instance=media_item)
    
    context = {
        'form': form,
        'media_item': media_item,
    }
    return render(request, 'media/edit_media.html', context)


@publicity_officer_required
def delete_media(request, pk):
    """Delete a media post"""
    media_item = get_object_or_404(MediaItem, pk=pk, uploaded_by=request.user)
    
    if request.method == 'POST':
        media_item.delete()
        messages.success(request, 'Media item deleted successfully!')
        return redirect('media:my_media')
    
    context = {
        'media_item': media_item,
    }
    return render(request, 'media/delete_media.html', context)


@specific_role_required('Director of Media & Publicity')
def review_media(request):
    """Review pending media submissions from publicity officers"""
    pending_media = MediaItem.objects.filter(status='PENDING').order_by('-created_at')
    
    context = {
        'pending_media': pending_media,
    }
    return render(request, 'media/review_media.html', context)


@specific_role_required('Director of Media & Publicity')
def approve_media(request, pk):
    """Approve a pending media item"""
    media_item = get_object_or_404(MediaItem, pk=pk, status='PENDING')
    
    if request.method == 'POST':
        media_item.status = 'APPROVED'
        media_item.approved_by = request.user
        media_item.save()
        messages.success(request, 'Media item approved and published to gallery!')
        return redirect('media:review_media')
    
    context = {
        'media_item': media_item,
    }
    return render(request, 'media/approve_media.html', context)


@specific_role_required('Director of Media & Publicity')
def reject_media(request, pk):
    """Reject a pending media item"""
    media_item = get_object_or_404(MediaItem, pk=pk, status='PENDING')
    
    if request.method == 'POST':
        media_item.status = 'REJECTED'
        media_item.save()
        messages.success(request, 'Media item rejected.')
        return redirect('media:review_media')
    
    context = {
        'media_item': media_item,
    }
    return render(request, 'media/reject_media.html', context)
