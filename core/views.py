from django.shortcuts import render
from django.http import HttpResponse

def home(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kebbi Progressive Network (KPN)</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f4f4f4; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #28a745; }
            .motto { color: #0066cc; font-style: italic; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔥 Kebbi Progressive Network (KPN) 🔥</h1>
            <p class="motto">One Voice, One Change</p>
            <p>Welcome to the official Kebbi Progressive Network website.</p>
            <p>The platform is currently under development and will be available soon!</p>
            <hr>
            <p><strong>System Status:</strong> ✅ Active</p>
            <p><small>Database: 3 Zones | 21 LGAs | 225 Wards | 41 Leadership Roles</small></p>
        </div>
    </body>
    </html>
    """)
