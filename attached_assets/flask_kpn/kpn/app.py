from flask import Flask, request
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from datetime import timedelta
import os
from extensions import db, login_manager

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32))
    
    # Database URL with compatibility handling
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///kpn2020.db')
    # Handle postgres:// vs postgresql:// compatibility (Heroku legacy format)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    
    # PostgreSQL connection pool settings for production stability
    if database_url.startswith('postgresql://'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,  # Validate connections before use
            'pool_recycle': 300,    # Recycle connections every 5 minutes
            'pool_timeout': 30,     # Timeout for getting connection from pool
            'max_overflow': 20      # Allow extra connections beyond pool_size
        }
    
    # Caching Configuration
    app.config['CACHE_TYPE'] = 'simple'  # Use Redis in production: 'redis'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default cache timeout
    
    # Security Configuration
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['WTF_CSRF_TIME_LIMIT'] = None
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file upload
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf = CSRFProtect(app)
    cache = Cache(app)
    login_manager.login_view = 'staff.login'  # type: ignore
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Make cache available globally
    app.cache = cache
    
    # Add static content caching headers for performance
    @app.after_request
    def add_cache_headers(response):
        # Cache static assets for 1 hour
        if request.endpoint and 'static' in request.endpoint:
            response.cache_control.max_age = 3600
            response.cache_control.public = True
        
        # Add no-cache headers for dynamic content
        elif request.endpoint and any(x in request.endpoint for x in ['dashboard', 'admin', 'edit']):
            response.cache_control.no_cache = True
            response.cache_control.no_store = True
            response.cache_control.must_revalidate = True
        
        return response
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    # Import and register blueprints
    from blueprints.core import core
    from blueprints.staff import staff
    from blueprints.leadership import leadership
    from blueprints.campaigns import campaigns
    from blueprints.donations import donations
    from blueprints.media import media
    from blueprints.events import events
    from blueprints.registration import registration
    from blueprints.duty_logs import duty_logs
    from blueprints.disciplinary import disciplinary
    from blueprints.messages import messages
    
    app.register_blueprint(core)
    app.register_blueprint(staff, url_prefix='/staff')
    app.register_blueprint(leadership, url_prefix='/leadership')
    app.register_blueprint(campaigns, url_prefix='/campaigns')
    app.register_blueprint(donations, url_prefix='/donations')
    app.register_blueprint(media, url_prefix='/media')
    app.register_blueprint(events, url_prefix='/events')
    app.register_blueprint(registration, url_prefix='/register')
    app.register_blueprint(duty_logs, url_prefix='/duties')
    app.register_blueprint(disciplinary, url_prefix='/disciplinary')
    app.register_blueprint(messages, url_prefix='/messages')
    
    # Create database tables and seed data (development only)
    # In production, use proper migrations and avoid auto-seeding
    if os.environ.get('FLASK_ENV') != 'production':
        with app.app_context():
            db.create_all()
            # Import and run seed data
            from seed_data import seed_database
            seed_database()
    
    return app

if __name__ == '__main__':
    app = create_app()
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug_mode)