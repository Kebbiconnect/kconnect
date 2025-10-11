# KPN Website Deployment Guide

## Environment Setup

### Required Environment Variables
```bash
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:password@host:port/database
FACEBOOK_APP_ID=your-facebook-app-id
FACEBOOK_APP_SECRET=your-facebook-app-secret
FLASK_ENV=production
```

### Database Configuration
- Development: SQLite (default)
- Production: PostgreSQL (recommended)
- Automatic schema creation on first run
- Seed data includes complete Kebbi State geographical structure

### File Upload Configuration
- Upload limit: 16MB
- Supported formats: Images (PNG, JPG, JPEG, GIF)
- Storage: Local filesystem (configurable)

## Production Deployment

### Server Requirements
- Python 3.8+
- PostgreSQL 12+
- 2GB RAM minimum
- 10GB storage minimum

### Security Configuration
- CSRF protection enabled
- Secure session cookies
- Password hashing with Werkzeug
- File upload validation
- Role-based access control

### Performance Considerations
- Database indexing on frequently queried columns
- Static file caching
- Session management optimization
- Image compression for uploads

## Backup and Maintenance
- Regular database backups
- Log rotation setup
- Security updates monitoring
- Performance monitoring