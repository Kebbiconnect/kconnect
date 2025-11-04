# Kebbi Progressive Network (KPN) - Django Application

## Overview

The Kebbi Progressive Network (KPN) is a comprehensive political/community organization management platform built with Django. The application manages a hierarchical political structure across Kebbi State, Nigeria, organizing members from State Executive level down through Zonal Coordinators, LGA Coordinators, to Ward Leaders. It provides tools for member management, campaign publishing, event coordination, financial tracking, media management, and hierarchical reporting systems.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture

**Framework**: Django 5.2.7 with Python 3.11.9

**Design Pattern**: Model-View-Template (MVT) - Django's standard architecture
- Models define database structure with PostgreSQL as the production database
- Views handle business logic and user interactions
- Templates render HTML with server-side template engine
- Custom decorators enforce role-based access control throughout the application

**Database**: PostgreSQL (via psycopg2-binary)
- Configured through dj-database-url for flexible deployment
- Uses Django ORM for all database interactions
- Database indexes on frequently queried fields (status, dates, foreign keys)
- Hierarchical data structures for geographical organization (Zone → LGA → Ward)

**Authentication & Authorization**:
- Custom User model extending Django's AbstractUser
- Role-based access control with hierarchical roles (STATE, ZONAL, LGA, WARD, GENERAL)
- Status-based approval workflow (PENDING → APPROVED → SUSPENDED/DISMISSED)
- Custom decorators: `@role_required`, `@specific_role_required`, `@approved_leader_required`
- Password reset via email tokens
- Rate limiting on login attempts (django-ratelimit)
- Failed login tracking (django-axes)

### Application Structure

**Modular App Design** - Django apps organized by domain:

1. **core** - Public-facing features and reporting system
   - Home page, about, leadership directory, FAQ
   - Hierarchical reporting system (Ward→LGA→Zonal→State)
   - Report statuses: DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED, FLAGGED, REJECTED, ESCALATED

2. **staff** - User management and authentication
   - Custom User model with role and status management
   - Member approval workflows
   - Role-specific dashboards for all 20+ leadership positions
   - Disciplinary action tracking with approval workflows
   - CSV/PDF member export capabilities
   - ID tag generation for members

3. **campaigns** - Content management for political campaigns
   - Campaign creation with approval workflow (DRAFT→PENDING→PUBLISHED/REJECTED)
   - Leader-only access for creating campaigns
   - Slug-based URLs for SEO
   - View tracking

4. **events** - Event and meeting management
   - Event calendar with CRUD operations
   - Attendance tracking with bulk operations
   - Meeting minutes recording and publishing
   - Organizing Secretary controls event creation

5. **donations** - Financial management
   - Three-tier financial workflow: Treasurer verifies → Financial Secretary records
   - Expense tracking by category
   - Financial report generation
   - Audit report submission (Auditor General → President)

6. **media** - Media and publicity management
   - Photo and video uploads with approval workflow
   - Publicity officers at all levels can upload
   - Director of Media & Publicity approves content
   - Automatic status assignment (Director uploads auto-approved)

7. **leadership** - Organizational structure
   - Zone, LGA, Ward geographical hierarchy
   - RoleDefinition system with tier-based positions
   - 20 State Executive positions, plus Zonal/LGA/Ward coordinator roles

### Frontend Architecture

**Template System**: Django templates with inheritance
- Base template with responsive navigation
- Dark mode support via Alpine.js and localStorage
- Mobile-first responsive design

**CSS Framework**: Tailwind CSS (via CDN)
- Utility-first approach for rapid UI development
- Custom color scheme (kpn-green, kpn-blue)
- Dark mode classes

**JavaScript**:
- Alpine.js for reactive components (dropdowns, modals, dark mode toggle)
- Vanilla JS for AJAX operations (role availability checks, cascading dropdowns)
- No heavy frontend framework - server-side rendering preferred

**Progressive Web App (PWA)**:
- Service worker for offline caching
- Web app manifest for installability
- Cache-first strategy for static assets

### Data Storage

**Media Files**:
- Cloudinary integration for image/video storage
- django-cloudinary-storage handles uploads
- Local filesystem fallback during development
- ImageKit for image processing (thumbnails)

**Static Files**:
- WhiteNoise for static file serving in production
- Compressed and cached static assets
- CDN usage for external libraries (Tailwind, Alpine.js, Font Awesome)

### Key Architectural Decisions

**Hierarchical Role System**:
- **Problem**: Complex organizational structure with multiple tiers
- **Solution**: Separate `role` field (tier level) and `role_definition` FK (specific position)
- **Rationale**: Allows flexible querying by tier while maintaining specific position assignments
- **Pros**: Easy filtering by tier, prevents duplicate position holders
- **Cons**: Two-field system adds slight complexity

**Approval Workflows**:
- **Problem**: Need content moderation and multi-step processes
- **Solution**: Status fields on models (User, Campaign, Donation, MediaItem) with workflow-specific transitions
- **Rationale**: Standardized pattern across all content types
- **Pros**: Consistent UX, easy to audit, clear permissions
- **Cons**: Can't easily revert status changes

**Cascading Geography**:
- **Problem**: Users belong to specific Ward/LGA/Zone combinations
- **Solution**: AJAX-based cascading dropdowns that filter options based on parent selection
- **Rationale**: Prevents invalid geography assignments
- **Pros**: Data integrity, better UX
- **Cons**: JavaScript dependency for registration

**Report Escalation**:
- **Problem**: Reports need to flow up the hierarchy
- **Solution**: `parent_report` self-referential FK creates report chains
- **Rationale**: Preserves original reports while creating new ones at higher levels
- **Pros**: Full audit trail, flexible workflows
- **Cons**: More complex queries

**Role-Based Access Control**:
- **Problem**: Different features for different roles
- **Solution**: Decorator-based permissions with custom decorators
- **Rationale**: Explicit, reusable, fails closed
- **Pros**: Clear permission requirements, easy to audit
- **Cons**: Requires decorators on every protected view

## External Dependencies

### Third-Party Services

**Cloudinary** - Media storage and CDN
- Handles image/video uploads and transformations
- Configured via environment variables (CLOUDINARY_URL)
- Used for: profile photos, campaign images, gallery media

**Email Service** (configured but not specified)
- Password reset emails
- Potentially member notifications
- Configured via Django EMAIL_* settings

### Database

**PostgreSQL** (production)
- Primary data store
- Accessed via psycopg2-binary adapter
- Connection managed by dj-database-url

### CDN Resources

- **Tailwind CSS**: https://cdn.tailwindcss.com
- **Alpine.js**: https://cdn.jsdelivr.net/npm/alpinejs
- **Font Awesome**: https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css

### Python Packages

**Core Framework**:
- Django 5.2.7
- gunicorn 23.0.0 (WSGI server)

**Forms & UI**:
- django-crispy-forms with crispy-bootstrap5
- django-imagekit for image processing

**Security**:
- django-axes (login attempt tracking)
- django-ratelimit (rate limiting)
- python-decouple (environment variable management)

**File Storage**:
- cloudinary
- django-cloudinary-storage
- pillow (image processing)

**Utilities**:
- python-docx (document generation)
- qrcode (likely for ID tags)
- reportlab (PDF generation)
- lxml (XML processing)

**PWA Support**:
- django-pwa

### Deployment Platforms

Configured for:
- **Render** (RENDER_EXTERNAL_HOSTNAME)
- **Replit** (REPLIT_DOMAINS)
- Local development

### Environment Variables Required

- `SESSION_SECRET` - Django secret key
- `DEBUG` - Debug mode toggle
- `DATABASE_URL` - PostgreSQL connection string
- `CLOUDINARY_URL` - Cloudinary API credentials
- `RENDER_EXTERNAL_HOSTNAME` - Render deployment URL
- `REPLIT_DOMAINS` - Replit deployment domains