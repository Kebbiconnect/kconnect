# Kebbi Progressive Network (KPN) Website

## Overview
The Kebbi Progressive Network (KPN) website is a Django-based civic engagement platform for youth mobilization, charity, welfare, and governance advocacy in Kebbi State, Nigeria. It aims to provide a robust system for member management, campaign dissemination, and financial transparency, fostering a unified voice for change.

## User Preferences
- Mobile-first design approach
- Dark mode toggle required
- Brand colors: Green, White, Blue
- Professional, clean UI
- Accessibility considerations

## System Architecture

### UI/UX Decisions
The platform adopts a mobile-first design using Tailwind CSS for responsiveness and Alpine.js for interactivity. It incorporates KPN's official colors (Green, White, Blue) and includes a dark mode toggle. Navigation features a professional bar with the KPN logo and a mobile menu. Public pages include Home, About Us, Leadership directory, News & Campaigns, Media Gallery, Contact, Support Us, FAQ, and Code of Conduct.

### Technical Implementations
Built on Django 5.2.7, the system is modularized into `core`, `staff`, `leadership`, `campaigns`, `donations`, `media`, and `events` applications. It features a custom `User` model with a role-based authentication and authorization system supporting 41 leadership roles across State, Zonal, LGA, and Ward tiers, each with distinct dashboards and permissions. Registration includes dynamic cascading dropdowns for location, real-time vacancy checking, gender collection, and mandatory Facebook page follow verification, enforcing strict seat limits.

### Feature Specifications
- **Public Pages**: Static and informational content.
- **User Management**: Custom user model, role-based permissions, disciplinary actions (Warning, Suspension, Dismissal with two-tier approval, including Legal & Ethics Adviser review), and full member management.
- **Organizational Hierarchy**: Models for Zone, LGA, Ward, and `RoleDefinition` with seat limits and vacancy checks.
- **Campaigns**: Campaign and publicity system with a status workflow (DRAFT, PENDING, PUBLISHED, REJECTED) and image uploads.
- **Dashboards**: Role-specific dashboards for all 41 leadership positions, tailored to their jurisdiction and responsibilities (e.g., President's dashboard for staff management, member approval; Director of Mobilization for member filtering and export).
- **Registration**: Enhanced form with locked cascading dropdowns, real-time AJAX vacancy checking, mandatory Facebook verification, and gender field.
- **Hierarchical Reporting System**: Report submission (Ward → LGA Coordinator → Zonal Coordinator → State President) with a status workflow (DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED/FLAGGED), deadline management, and role-based access control.
- **Member Mobilization Tools**: Advanced member filtering (by Zone, LGA, Ward, Role, Gender, Status), CSV export of contact lists, and dedicated interfaces for Women Leaders.
- **Women's Programs Management**: CRUD for women-focused programs (workshops, training) with jurisdiction-based access, participant management, and budget tracking.
- **FAQ Management System**: CRUD for FAQs with content management, status control, and organization by Assistant General Secretary.
- **Legal & Ethics Oversight**: Two-tier approval workflow for disciplinary actions requiring both State President and Legal & Ethics Adviser review, including legal opinion documentation.
- **Finance Management**: Donation verification workflow (UNVERIFIED → Treasurer → Financial Secretary), expense tracking, and automated financial report generation.
- **Media Management**: Gallery for photos/videos with upload and approval.
- **Events**: Full event management system including creation, calendar, attendance logging, and meeting minutes recording.
- **Youth Development Programs**: Management of youth-focused programs with participant tracking, budget, and impact reporting.
- **Welfare Programs**: Management of welfare programs (health, financial aid) with beneficiary tracking, budget, and funds disbursed monitoring.
- **Audit Reports**: Auditor General can create, edit, and submit audit reports to the President with findings, recommendations, and file uploads, with read-only access to financial data.
- **Vice President Tools**: Inter-zone reports, comprehensive staff directory with advanced filtering, and read-only disciplinary case review panel.

### System Design Choices
- **Database**: SQLite (development), LibSQL via Turso (production) with `django-libsql`.
- **Authentication**: Robust login, logout, registration with extensive validation.
- **Access Control**: `@role_required` and `@specific_role_required` decorators for secure, role-based access.
- **Static Files**: Managed via Django's static files system.
- **Error Handling**: Comprehensive validation for location and role IDs.

## External Dependencies
- **Database**: SQLite, LibSQL (via Turso)
- **Image Processing**: Pillow
- **Environment Variables**: python-decouple