# Kebbi Progressive Network (KPN) Website

## Overview
The Kebbi Progressive Network (KPN) website is a comprehensive Django-based civic engagement platform designed for youth mobilization, charity, welfare, and governance advocacy across Kebbi State, Nigeria.

**Motto:** One Voice, One Change

**Status:** Phase 1 - Foundation Complete ✅

## Recent Changes (October 11, 2025)

### Completed
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
- ✅ Set up basic homepage and URL routing
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

### Key Features (To Be Implemented)

#### Dynamic Registration
- Real-time vacancy checking based on applicant location
- Only vacant leadership positions shown in dropdown
- Facebook verification step (mandatory)
- Auto-approval for General Members
- Manual approval required for Leadership roles

#### Hierarchical Approval Workflow
- Ward → LGA → Zonal → State reporting chain
- Supervisors approve applications within jurisdiction
- State President has final authority

#### Role-Specific Dashboards
- 20+ unique dashboard configurations
- Custom features per leadership role
- Approval queues, reporting tools, analytics

#### Public Pages
- Home (featured campaigns, latest news)
- About Us (Full KPN Constitution)
- Leadership (filterable by Zone/LGA/Ward, shows vacant seats)
- Join Us (registration with dynamic vacancy checking)
- News & Campaigns (blog-style)
- Media Gallery (approved photos/videos)
- Contact (inquiry form)
- Support Us (bank account details)
- FAQ (accordion-style)
- Code of Conduct

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
