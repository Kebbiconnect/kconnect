# Kebbi Progressive Network (KPN) Website

## Overview
The Kebbi Progressive Network (KPN) website is a comprehensive Django-based civic engagement platform designed for youth mobilization, charity, welfare, and governance advocacy across Kebbi State, Nigeria.

**Motto:** One Voice, One Change

**Status:** Phase 5 - Complete Dashboard System & Enhanced Registration ✅

## Recent Changes (October 11, 2025)

### Phase 5 Completed (Latest)
- ✅ **Complete Dashboard System**: Implemented all 41 leadership role dashboards
  - **State Executive (20 roles)**: All dashboard views and templates created with role-specific features
  - **Zonal Coordinators (3 roles)**: Zonal Coordinator, Secretary, Publicity Officer dashboards complete
  - **LGA Coordinators (10 roles)**: All LGA leadership dashboards with jurisdiction-specific data
  - **Ward Leaders (8 roles)**: All ward leadership dashboards fully implemented
  - **URL Routing**: Comprehensive routing system maps all 41 roles to appropriate dashboards
  - **Role Mapping**: Intelligent dashboard routing handles duplicate role titles across tiers

- ✅ **Enhanced Registration Form**: Improved UX with locked cascading dropdowns
  - **Locked Dropdowns**: LGA disabled until Zone selected, Ward disabled until LGA selected
  - **Role Selection**: Role dropdown disabled until location hierarchy is complete
  - **Facebook Verification**: Submit button hidden until Facebook page follow checkbox is checked
  - **Progressive Disclosure**: Dropdowns unlock sequentially as user makes selections
  - **Real-time Validation**: Seat availability checking before allowing role selection

### Phase 4 Completed
- ✅ **Flask Template Migration Complete**: Successfully migrated all public pages and registration form from Flask reference project to Django
  - **About Us Page**: Complete migration with Vision, Mission, Organizational Structure (4 cards), and Core Principles
  - **Code of Conduct**: Comprehensive content including Core Principles (4 cards), Prohibited Behaviors (3 sections), Expected Standards (4 accordions), and Reporting/Enforcement procedures
  - **FAQ Page**: Complete with search functionality, category filtering (All, Membership, Leadership, Activities, Support), and 12 detailed FAQ items with accordion behavior
  - **Registration Form**: Enhanced with animated dropdowns and dynamic features:
    - Cascading location selection (Zone → LGA → Ward) using vanilla JavaScript
    - Real-time API integration for location data fetching
    - Dynamic role options based on selected location
    - Seat availability checking via AJAX
    - Profile photo upload field
    - Mandatory Facebook page follow verification
    - Form validation and error handling

### Phase 3 Completed
- ✅ **AJAX Vacancy Checking API**: Real-time role availability checking with cascading location dropdowns (fixed zone selection bug)
- ✅ **Core Dashboard Infrastructure**: Role-based routing system with permission decorators (@role_required, @specific_role_required)
- ✅ **President Dashboard**: Full staff management and oversight features
  - Dashboard overview with key statistics (pending approvals, total members, leaders, reports)
  - Member approval workflow with jurisdiction filtering (Zone/LGA/Ward filters)
  - Review applicant interface with approve/reject actions
  - Comprehensive staff directory with search and filtering
  - Reports viewing system for hierarchical reports
  - Disciplinary actions management interface

### Phase 2 Completed
- ✅ **Tailwind CSS Integration**: Responsive design with KPN brand colors (Green/White/Blue) and dark mode toggle
- ✅ **Base Template**: Professional navigation bar with logo, mobile menu, footer with social links
- ✅ **All Public Pages Built**:
  - Home page with hero section and statistics
  - About Us (KPN Constitution)
  - Leadership directory (filterable by Zone/LGA/Ward)
  - News & Campaigns blog
  - Media Gallery (photos/videos)
  - Contact form
  - Support Us (donation info)
  - FAQ (accordion-style)
  - Code of Conduct
- ✅ **Authentication System**: Login, logout, registration with comprehensive validation
- ✅ **Dynamic Registration**: Vacancy checking with mandatory Facebook verification
- ✅ **Role-Based Dashboard**: Dashboard and profile views with quick actions
- ✅ **Security Hardening**: Comprehensive validation for zone/LGA/ward/role IDs (handles DoesNotExist, ValueError, TypeError)
- ✅ **Vacancy Enforcement**: Required location fields per role tier (STATE needs zone+LGA, ZONAL needs zone, etc.)

### Phase 1 Completed
- ✅ Django 5.2 project setup with LibSQL/Turso database support (fallback to SQLite for development)
- ✅ Created 7 modular Django apps: core, staff, leadership, campaigns, donations, media, events
- ✅ Built custom User model with role-based authentication and location hierarchy
- ✅ Created location models (Zone, LGA, Ward) and RoleDefinition model
- ✅ Successfully seeded database:
  - 3 Zones (Kebbi North, Central, South)
  - 21 LGAs
  - 225 Wards
  - 41 Leadership Role Definitions
- ✅ Configured Django admin with all models registered
- ✅ Created superuser account (admin/admin123)
- ✅ Server running successfully on port 5000

### Database Configuration
- **Development:** SQLite (db.sqlite3)
- **Production:** LibSQL via Turso (set USE_TURSO=True)
- **Connection:** libsql://kpntursodb-kpntursodb.aws-eu-west-1.turso.io

## Project Architecture

### Django Apps Structure

#### 1. **core** - Public Pages
- Static content (Home, About, FAQ, Code of Conduct)
- Report model for hierarchical reporting system
- Public-facing templates

#### 2. **staff** - User Management
- Custom User model extending AbstractUser
- Role-based permissions (STATE, ZONAL, LGA, WARD, GENERAL)
- DisciplinaryAction model
- Authentication & profile management

#### 3. **leadership** - Organizational Hierarchy
- Zone, LGA, Ward models
- RoleDefinition model
- Seat limit enforcement
- Vacancy checking logic

#### 4. **campaigns** - News & Campaigns CMS
- Campaign/Article model with approval workflow
- Featured images
- Status: DRAFT, PENDING, PUBLISHED, REJECTED

#### 5. **donations** - Finance Management
- Donation model (two-step verification/recording)
- FinancialReport model
- Treasurer → Financial Secretary workflow

#### 6. **media** - Photo/Video Gallery
- MediaItem model (PHOTO/VIDEO types)
- Upload and approval workflow
- Director of Media & Publicity manages approvals

#### 7. **events** - Private Calendar & Attendance
- Event model
- EventAttendance with manual logging
- Leader-only access

### Leadership Structure

#### State Executive Council (20 seats)
1. President
2. Vice President
3. General Secretary
4. Assistant General Secretary
5. State Supervisor
6. Legal & Ethics Adviser
7. Treasurer
8. Financial Secretary
9. Director of Mobilization
10. Assistant Director of Mobilization
11. Organizing Secretary
12. Assistant Organizing Secretary
13. Auditor General
14. Welfare Officer
15. Youth Development & Empowerment Officer
16. Women Leader
17. Assistant Women Leader
18. Director of Media & Publicity
19. Assistant Director of Media & Publicity
20. Public Relations & Community Engagement Officer

#### Zonal Coordinators (3 per Zone)
1. Zonal Coordinator
2. Zonal Secretary
3. Zonal Publicity Officer

#### LGA Coordinators (10 per LGA)
1. LGA Coordinator
2. Secretary
3. Organizing Secretary
4. Treasurer
5. Publicity Officer
6. LGA Supervisor
7. Women Leader
8. Welfare Officer
9. Director of Contact and Mobilization
10. LGA Adviser

#### Ward Leaders (8 per Ward)
1. Ward Coordinator
2. Secretary
3. Organizing Secretary
4. Treasurer
5. Publicity Officer
6. Financial Secretary
7. Ward Supervisor
8. Ward Adviser

### Key Features

#### Implemented ✅
- ✅ **Public Pages**: Home, About Us, Leadership directory, News & Campaigns, Media Gallery, Contact, Support Us, FAQ, Code of Conduct
- ✅ **Dynamic Registration**: Real-time vacancy checking based on applicant location with Facebook verification requirement
- ✅ **Authentication System**: Login, logout, secure registration with comprehensive validation
- ✅ **Role-Based Access**: Dashboard and profile views with role-specific quick actions
- ✅ **Vacancy Enforcement**: Location fields required per role tier, prevents duplicate leadership applications
- ✅ **Dashboard Infrastructure**: Role-based routing and permission decorators for secure access control
- ✅ **President Dashboard**: Full staff management, member approval workflow with jurisdiction filtering, reports viewing, disciplinary actions

#### Completed ✅
- ✅ **All 41 Leadership Dashboards**: Complete dashboard system for every role in the organization
- ✅ **Enhanced Registration**: Locked cascading dropdowns with Facebook verification
- ✅ **Role-Based Routing**: Comprehensive URL routing for all dashboard types
- ✅ **Director of Media & Publicity Dashboard**: Member/campaign/media approval queues
- ✅ **Treasurer & Financial Secretary Dashboards**: Donation workflow management
- ✅ **Organizing Secretary Dashboards**: Event creation and attendance logging

#### To Be Implemented
- **Hierarchical Approval Workflow**: Ward → LGA → Zonal → State reporting chain
- **Advanced Dashboard Features**: Custom features per leadership role
- **News & Campaigns Management**: Approval queue for campaigns and articles
- **Media Gallery Management**: Upload and approval workflow for photos/videos
- **Events & Calendar**: Private calendar with attendance logging
- **Hierarchical Reporting**: Multi-level reporting system
- **Finance Management**: Donation tracking and financial reporting

## Technology Stack

**Backend:**
- Django 5.2.7
- django-libsql (LibSQL/Turso support)
- Pillow (image processing)
- python-decouple (environment variables)

**Frontend (To Be Added):**
- Django Templates
- Tailwind CSS (mobile-first, dark mode)
- Alpine.js (lightweight interactivity)

**Database:**
- Development: SQLite
- Production: LibSQL (Turso)

## Development Commands

```bash
# Run development server
python manage.py runserver 0.0.0.0:5000

# Seed database
python manage.py seed_data

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Access admin panel
# URL: /admin/
# Username: admin
# Password: admin123
```

## Environment Variables

- `SESSION_SECRET` - Django secret key
- `TURSO_AUTH_TOKEN` - Turso database authentication token
- `USE_TURSO` - Set to True to use Turso database (default: False)

## Branding

**Colors:**
- 🟢 Green: Progress, Growth
- ⚪ White: Peace, Unity
- 🔵 Blue: Trust, Stability

**Timezone:** Africa/Lagos

## Next Phase Tasks

1. Build authentication system (login, logout, registration)
2. Implement dynamic registration with vacancy checking
3. Create hierarchical approval workflows
4. Build role-specific dashboards for all 20+ roles
5. Implement News & Campaigns with approval queue
6. Build Media Gallery with upload/approval workflow
7. Create Events & Calendar with attendance logging
8. Implement hierarchical reporting system
9. Build finance management workflows
10. Set up Tailwind CSS with KPN branding
11. Create complete template system
12. Integrate KPN logo
13. Add mobile responsiveness and dark mode
14. Testing and deployment configuration

## User Preferences
- Mobile-first design approach
- Dark mode toggle required
- Brand colors: Green, White, Blue
- Professional, clean UI
- Accessibility considerations

## Notes
- General Members have no dashboard - profile access only
- Leadership positions enforce strict seat limits
- All media/content requires approval before publication
- Facebook page follow is mandatory for registration verification
- System prevents applications for filled leadership seats
