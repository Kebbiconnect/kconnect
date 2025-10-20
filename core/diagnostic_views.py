"""
Web-based diagnostic views for production debugging
Access via /diagnostics/ in production
"""
from django.http import HttpResponse
from django.conf import settings
import os

def cloudinary_diagnostics(request):
    """
    Web-based diagnostics for Cloudinary configuration
    Access this at: https://your-app.onrender.com/diagnostics/
    """
    
    # Collect diagnostic information
    diagnostics = []
    
    diagnostics.append("=" * 70)
    diagnostics.append("🔍 CLOUDINARY DIAGNOSTICS")
    diagnostics.append("=" * 70)
    diagnostics.append("")
    
    # Check 1: DEBUG Setting
    diagnostics.append("1️⃣ DEBUG Setting:")
    diagnostics.append(f"   DEBUG = {settings.DEBUG}")
    if settings.DEBUG:
        diagnostics.append("   ⚠️ WARNING: Should be False in production")
    else:
        diagnostics.append("   ✅ Production mode")
    diagnostics.append("")
    
    # Check 2: Environment Variables
    diagnostics.append("2️⃣ Cloudinary Environment Variables:")
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    
    if cloud_name:
        diagnostics.append(f"   ✅ CLOUDINARY_CLOUD_NAME = {cloud_name}")
    else:
        diagnostics.append("   ❌ CLOUDINARY_CLOUD_NAME is MISSING!")
    
    if api_key:
        diagnostics.append(f"   ✅ CLOUDINARY_API_KEY = {api_key[:10]}... (hidden)")
    else:
        diagnostics.append("   ❌ CLOUDINARY_API_KEY is MISSING!")
    
    if api_secret:
        diagnostics.append(f"   ✅ CLOUDINARY_API_SECRET = {api_secret[:10]}... (hidden)")
    else:
        diagnostics.append("   ❌ CLOUDINARY_API_SECRET is MISSING!")
    
    diagnostics.append("")
    
    # Check 3: Django Storage Settings
    diagnostics.append("3️⃣ Django File Storage:")
    diagnostics.append(f"   DEFAULT_FILE_STORAGE = {settings.DEFAULT_FILE_STORAGE}")
    
    if 'cloudinary' in settings.DEFAULT_FILE_STORAGE.lower():
        diagnostics.append("   ✅ Using Cloudinary for media files")
    else:
        diagnostics.append("   ❌ NOT using Cloudinary for media files!")
    
    diagnostics.append("")
    
    # Check 4: URL Configuration
    diagnostics.append("4️⃣ URL Configuration:")
    diagnostics.append(f"   MEDIA_URL = {settings.MEDIA_URL}")
    
    if 'cloudinary.com' in settings.MEDIA_URL:
        diagnostics.append("   ✅ MEDIA_URL points to Cloudinary")
    else:
        diagnostics.append("   ❌ MEDIA_URL does NOT point to Cloudinary!")
    
    diagnostics.append(f"   STATIC_URL = {settings.STATIC_URL}")
    diagnostics.append("")
    
    # Check 5: Cloudinary Storage Config
    diagnostics.append("5️⃣ Cloudinary Storage Configuration:")
    if hasattr(settings, 'CLOUDINARY_STORAGE'):
        diagnostics.append("   ✅ CLOUDINARY_STORAGE configured")
        if 'CLOUD_NAME' in settings.CLOUDINARY_STORAGE:
            diagnostics.append(f"      Cloud Name: {settings.CLOUDINARY_STORAGE['CLOUD_NAME']}")
    else:
        diagnostics.append("   ❌ CLOUDINARY_STORAGE NOT configured!")
    
    diagnostics.append("")
    
    # Check 6: Test Upload
    diagnostics.append("6️⃣ Testing Cloudinary Upload:")
    try:
        import cloudinary
        import cloudinary.uploader
        from io import BytesIO
        from PIL import Image
        
        # Create test image
        img = Image.new('RGB', (10, 10), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            img_bytes,
            folder="diagnostic_test",
            public_id="test_production"
        )
        
        diagnostics.append("   ✅ Upload SUCCESSFUL!")
        diagnostics.append(f"      URL: {result['secure_url']}")
        
        # Clean up
        cloudinary.uploader.destroy(result['public_id'])
        diagnostics.append("   ✅ Test file cleaned up")
        
    except Exception as e:
        diagnostics.append("   ❌ Upload FAILED!")
        diagnostics.append(f"      Error: {str(e)}")
    
    diagnostics.append("")
    
    # Check 7: Sample Image URLs
    diagnostics.append("7️⃣ Sample Image URLs from Database:")
    try:
        from staff.models import User
        
        users_with_photos = User.objects.filter(photo__isnull=False).exclude(photo='')[:3]
        
        if users_with_photos.exists():
            for user in users_with_photos:
                try:
                    url = user.photo.url
                    diagnostics.append(f"   User: {user.get_full_name()}")
                    diagnostics.append(f"   Photo URL: {url}")
                    
                    if 'cloudinary.com' in url:
                        diagnostics.append("   ✅ Uses Cloudinary URL")
                    else:
                        diagnostics.append("   ❌ Uses local URL")
                    diagnostics.append("")
                except Exception as e:
                    diagnostics.append(f"   ❌ Error: {str(e)}")
        else:
            diagnostics.append("   ℹ️ No users with photos in database")
    except Exception as e:
        diagnostics.append(f"   ❌ Error checking database: {str(e)}")
    
    diagnostics.append("")
    diagnostics.append("=" * 70)
    diagnostics.append("📊 DIAGNOSIS COMPLETE")
    diagnostics.append("=" * 70)
    
    # Return as plain text
    response = HttpResponse("\n".join(diagnostics), content_type="text/plain")
    return response
