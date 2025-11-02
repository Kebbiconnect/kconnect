from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import MediaItem
from .forms import OpinionUploadForm, MediaItemEditForm
from staff.decorators import specific_role_required
import os


@specific_role_required('Director of Media & Publicity')
def create_opinion(request):
    """Create opinions (media posts) with multiple file uploads"""
    if request.method == 'POST':
        form = OpinionUploadForm(request.POST, request.FILES)
        files = request.FILES.getlist('files')
        
        if form.is_valid() and files:
            caption = form.cleaned_data['caption']
            uploaded_count = 0
            
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
                
                # Create media item
                media_item = MediaItem.objects.create(
                    title=f"Opinion by {request.user.get_full_name()}",
                    description=caption,
                    media_type=media_type,
                    file=file,
                    uploaded_by=request.user,
                    status='APPROVED',  # Auto-approve for Director Media & Publicity
                    approved_by=request.user
                )
                uploaded_count += 1
            
            if uploaded_count > 0:
                messages.success(request, f'Successfully uploaded {uploaded_count} media file(s) to the gallery!')
                return redirect('media:my_opinions')
            else:
                messages.error(request, 'No valid media files were uploaded.')
        else:
            if not files:
                messages.error(request, 'Please select at least one file to upload.')
    else:
        form = OpinionUploadForm()
    
    return render(request, 'media/create_opinion.html', {'form': form})


@specific_role_required('Director of Media & Publicity')
def my_opinions(request):
    """List all media opinions uploaded by the Director of Media & Publicity"""
    opinions = MediaItem.objects.filter(uploaded_by=request.user).order_by('-created_at')
    
    context = {
        'opinions': opinions,
    }
    return render(request, 'media/my_opinions.html', context)


@specific_role_required('Director of Media & Publicity')
def edit_opinion(request, pk):
    """Edit a media opinion"""
    opinion = get_object_or_404(MediaItem, pk=pk, uploaded_by=request.user)
    
    if request.method == 'POST':
        form = MediaItemEditForm(request.POST, instance=opinion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Media item updated successfully!')
            return redirect('media:my_opinions')
    else:
        form = MediaItemEditForm(instance=opinion)
    
    context = {
        'form': form,
        'opinion': opinion,
    }
    return render(request, 'media/edit_opinion.html', context)


@specific_role_required('Director of Media & Publicity')
def delete_opinion(request, pk):
    """Delete a media opinion"""
    opinion = get_object_or_404(MediaItem, pk=pk, uploaded_by=request.user)
    
    if request.method == 'POST':
        opinion.delete()
        messages.success(request, 'Media item deleted successfully!')
        return redirect('media:my_opinions')
    
    context = {
        'opinion': opinion,
    }
    return render(request, 'media/delete_opinion.html', context)
