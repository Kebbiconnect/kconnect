# KPN Website

## Overview
The Kebbi Progressive Network (KPN) website is a Django-based civic engagement platform designed for youth mobilization, charity, welfare initiatives, and governance advocacy in Kebbi State, Nigeria. Its primary purpose is to provide a robust system for managing members, disseminating campaigns, and ensuring financial transparency, thereby unifying efforts for societal change. The platform is production-ready and fully operational.

## Recent Changes (October 2025)
- **Production Deployment Ready**: Complete Railway + Neon Database deployment configuration with all security hardening in place. Deployment files created: requirements.txt, Procfile, railway.json, .env templates, and comprehensive deployment guides.
- **Critical Bug Fix - Kebbi South Wards**: Fixed registration form bug where Kebbi South zone failed to load wards. Root cause was LGA naming mismatch ("Danko/Wasagu" vs "Wasagu/Danko"). All 71 wards now properly populated across all 7 Kebbi South LGAs.
- **Enhanced Registration Form**: Replaced Facebook verification checkbox with interactive button that opens KPN's Facebook page in new tab and auto-enables Submit button upon click. Uses localStorage for persistence across page refreshes, with automatic cleanup on successful registration.
- **Smart Tier Selection**: Implemented auto-hide functionality that only displays leadership tiers with vacant positions. Tiers with all seats filled are completely hidden from the dropdown.
- **Statewide Role Clarification**: State Executive roles now clearly marked as "(statewide)" in the UI, indicating they are available to all members regardless of their specific zone or LGA location.
- **Password Management**: Implemented comprehensive password management system:
  - Change Password: Secure password change functionality with current password verification, accessible from user profiles
  - Forgot Password: Email-based password reset using Django's token-based authentication system
  - Reset Password: Secure URL-based password reset with password strength indicator and matching validation
  - Email Integration: Console backend for development, configurable SMTP for production via environment variables
- **UI/UX Enhancements**: Modernized three key pages with professional designs:
  - Contact Page: Gradient backgrounds, floating animations, interactive info cards, social media links
  - News/Campaigns Page: Card-based layout with shimmer effects, hover animations, image overlays, and CTA section
  - Media Gallery: Advanced grid layout with lightbox functionality for photos, filter buttons, hover effects, and upload CTA

## User Preferences
- Mobile-first design approach
- Dark mode toggle required
- Brand colors: Green, White, Blue
- Professional, clean UI
- Accessibility considerations

## System Architecture

### UI/UX Decisions
The platform utilizes a mobile-first design philosophy, implemented with Tailwind CSS for responsiveness and Alpine.js for interactive elements. It adheres to KPN's official color palette (Green, White, Blue) and incorporates a dark mode toggle for user preference. Navigation is streamlined with a professional bar featuring the KPN logo and a dedicated mobile menu. Public-facing pages include Home, About Us, Leadership, News & Campaigns, Media Gallery, Contact, Support Us, FAQ, and Code of Conduct. Animations and micro-interactions are integrated across the site, including login, mobile menus, and dashboards, to enhance user experience.

### Technical Implementations
The system is built on Django and structured into modular applications: `core`, `staff`, `leadership`, `campaigns`, `donations`, `media`, and `events`. It features a custom `User` model with a comprehensive role-based authentication and authorization system, supporting 41 distinct leadership roles across State, Zonal, LGA, and Ward tiers. Each role is assigned a specific dashboard and permissions. The registration process includes dynamic cascading dropdowns for location selection, real-time vacancy checks, gender collection, and interactive Facebook page follow verification via button (with localStorage persistence). The tier selection system automatically hides tiers with no vacant positions and clearly differentiates statewide roles (State Executive) from location-specific roles (Zonal, LGA, Ward).

### Feature Specifications
- **User Management**: Custom user model, role-based permissions, disciplinary actions (Warning, Suspension, Dismissal with two-tier approval), and full member management.
- **Organizational Hierarchy**: Models for Zone, LGA, Ward, and `RoleDefinition` with seat limits and vacancy checks.
- **Campaigns**: System for campaign and publicity management with a status workflow and image uploads.
- **Dashboards**: Role-specific dashboards for all 41 leadership positions, tailored to their jurisdiction and responsibilities.
- **Hierarchical Reporting System**: Automated report escalation (Ward → LGA → Zonal → State) with status workflow, email notifications, dashboard analytics, deadline management, and role-based access control.
- **Member Mobilization Tools**: Advanced member filtering, CSV export of contact lists.
- **Program Management**: Comprehensive CRUD systems for Women's Programs, Youth Development Programs, and Welfare Programs, including participant/beneficiary tracking, budget management, and secure IDOR-protected assignments.
- **FAQ Management System**: CRUD for FAQs with content management and status control.
- **Legal & Ethics Oversight**: Two-tier approval for disciplinary actions involving the State President and Legal & Ethics Adviser.
- **Finance Management**: Donation verification workflow, expense tracking, and automated financial reports.
- **Media Management**: Gallery for photos/videos with upload and approval.
- **Events**: Full event management system including creation, calendar, attendance logging, and meeting minutes.
- **Audit Reports**: Auditor General can create, edit, and submit audit reports with findings and recommendations, with read-only access to financial data.
- **Vice President Tools**: Inter-zone reports, staff directory, and disciplinary case review panel.
- **Community Outreach Management**: Tracking for community engagement activities including partnerships, meetings, and media collaborations.
- **Ward Meeting Logbook**: Management and tracking of ward-level meetings with attendance and minutes.

### System Design Choices
- **Database**: Neon PostgreSQL (production/development) with SSL connection, with fallback options.
- **Authentication**: Robust login, logout, and registration with extensive validation.
- **Access Control**: Utilizes `@role_required` and `@specific_role_required` decorators for secure, role-based access.
- **Static Files**: Managed via Django's static files system and served with WhiteNoise for optimization.
- **Error Handling**: Comprehensive validation for location and role IDs.

## External Dependencies
- **Database**: Neon PostgreSQL, SQLite, LibSQL (via Turso)
- **Database Driver**: psycopg2-binary
- **Image Processing**: Pillow
- **Environment Variables**: python-decouple