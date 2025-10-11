"""
Image optimization utilities for performance
"""
import os
from datetime import datetime
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename
import mimetypes


def optimize_image(image_path, max_width=800, max_height=600, quality=85):
    """
    Optimize image for web display
    
    Args:
        image_path: Path to the image file
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels 
        quality: JPEG quality (1-100)
    
    Returns:
        bool: True if optimization successful
    """
    try:
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Auto-orient image based on EXIF data
            img = ImageOps.exif_transpose(img)
            
            # Calculate new dimensions maintaining aspect ratio
            ratio = min(max_width / img.width, max_height / img.height)
            if ratio < 1:
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Save optimized image
            if image_path.lower().endswith(('.png', '.gif')):
                # Keep PNG/GIF format but optimize
                img.save(image_path, optimize=True)
            else:
                # Convert to JPEG for better compression
                base_path = os.path.splitext(image_path)[0]
                new_path = f"{base_path}.jpg"
                img.save(new_path, 'JPEG', quality=quality, optimize=True)
                
                # Remove original if different format
                if new_path != image_path:
                    os.remove(image_path)
                    return new_path
            
            return image_path
            
    except Exception as e:
        print(f"Error optimizing image {image_path}: {e}")
        return None


def create_thumbnail(image_path, thumb_size=(150, 150)):
    """
    Create thumbnail version of image
    
    Args:
        image_path: Path to the original image
        thumb_size: Tuple of (width, height) for thumbnail
    
    Returns:
        str: Path to thumbnail file or None if failed
    """
    try:
        # Generate thumbnail filename
        base_path, ext = os.path.splitext(image_path)
        thumb_path = f"{base_path}_thumb{ext}"
        
        with Image.open(image_path) as img:
            # Auto-orient image
            img = ImageOps.exif_transpose(img)
            
            # Create thumbnail maintaining aspect ratio
            img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            
            # Convert RGBA to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Save thumbnail
            img.save(thumb_path, 'JPEG', quality=90, optimize=True)
            return thumb_path
            
    except Exception as e:
        print(f"Error creating thumbnail for {image_path}: {e}")
        return None


def validate_and_process_upload(file, upload_dir, max_size_mb=5):
    """
    Validate, optimize and save uploaded image
    
    Args:
        file: Uploaded file object
        upload_dir: Directory to save the file
        max_size_mb: Maximum file size in MB
    
    Returns:
        dict: Result with 'success', 'filename', 'thumbnail', 'error' keys
    """
    result = {
        'success': False,
        'filename': None,
        'thumbnail': None,
        'error': None
    }
    
    if not file or not file.filename:
        result['error'] = 'No file selected'
        return result
    
    # Validate file extension
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        result['error'] = 'Invalid file type. Please upload PNG, JPG, JPEG, GIF, or WebP images.'
        return result
    
    # Validate MIME type
    mime_type, _ = mimetypes.guess_type(file.filename)
    allowed_mimes = {'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'}
    if mime_type not in allowed_mimes:
        result['error'] = 'Invalid file type detected.'
        return result
    
    # Check file size
    file.seek(0, os.SEEK_END)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    
    if size_mb > max_size_mb:
        result['error'] = f'File too large. Maximum size is {max_size_mb}MB.'
        return result
    
    try:
        # Generate secure filename
        filename = secure_filename(file.filename)
        timestamp = int(datetime.now().timestamp())
        base_name, ext = os.path.splitext(filename)
        filename = f"{base_name}_{timestamp}{ext}"
        
        # Save file
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Optimize image
        optimized_path = optimize_image(file_path)
        if optimized_path:
            # Update filename if format changed
            filename = os.path.basename(optimized_path)
            
            # Create thumbnail
            thumb_path = create_thumbnail(optimized_path)
            thumb_filename = os.path.basename(thumb_path) if thumb_path else None
            
            result.update({
                'success': True,
                'filename': filename,
                'thumbnail': thumb_filename
            })
        else:
            result['error'] = 'Failed to optimize image'
            
    except Exception as e:
        result['error'] = f'Upload failed: {str(e)}'
    
    return result


def get_image_info(image_path):
    """
    Get information about an image file
    
    Args:
        image_path: Path to image file
    
    Returns:
        dict: Image information or None if failed
    """
    try:
        with Image.open(image_path) as img:
            return {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode,
                'size_bytes': os.path.getsize(image_path)
            }
    except Exception:
        return None