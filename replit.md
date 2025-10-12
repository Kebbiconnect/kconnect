# Kebbi Progressive Network (KPN) Website

## Overview
The Kebbi Progressive Network (KPN) website is a comprehensive Django-based civic engagement platform for youth mobilization, charity, welfare, and governance advocacy across Kebbi State, Nigeria. Its primary purpose is to provide a robust system for member management, campaign dissemination, and financial transparency within the organization, with the ultimate ambition of fostering a unified voice for change.

## User Preferences
- Mobile-first design approach
- Dark mode toggle required
- Brand colors: Green, White, Blue
- Professional, clean UI
- Accessibility considerations

## System Architecture

### UI/UX Decisions
The platform utilizes a mobile-first design philosophy with Tailwind CSS for responsiveness and Alpine.js for lightweight interactivity. The branding incorporates KPN's official colors (Green, White, Blue) and includes a dark mode toggle. Navigation features a professional bar with the KPN logo and a mobile menu. Public-facing pages include Home, About Us, Leadership directory, News & Campaigns, Media Gallery, Contact, Support Us, FAQ, and Code of Conduct.

### Technical Implementations
The project is built on Django 5.2.7 and structured into seven modular applications: `core`, `staff`, `leadership`, `campaigns`, `donations`, `media`, and `events`. It features a custom `User` model with a comprehensive role-based authentication and authorization system, enabling distinct dashboards and permissions for 41 leadership roles across State, Zonal, LGA, and Ward tiers. Dynamic registration includes cascading dropdowns for location selection (Zone, LGA, Ward), real-time vacancy checking, and mandatory Facebook page follow verification. The system enforces strict seat limits for leadership positions and incorporates security measures for input validation.

### Feature Specifications
- **Public Pages**: Core static and informational content.
- **User Management (`staff` app)**: Custom user model, role-based permissions, disciplinary actions, and full member management capabilities for the President, including promotion, demotion, suspension, and role swapping.
- **Organizational Hierarchy (`leadership` app)**: Models for Zone, LGA, Ward, and `RoleDefinition`, enforcing seat limits and vacancy checking.
- **Campaigns (`campaigns` app)**: A comprehensive campaign and publicity system with a status workflow (DRAFT, PENDING, PUBLISHED, REJECTED), supporting featured image uploads and a dedicated approval process managed by the Director of Media & Publicity.
- **Dashboards**: Role-specific dashboards for all 41 leadership positions, providing tailored functionalities and data relevant to their jurisdiction and responsibilities. The President's dashboard includes staff management, member approval workflow, and reporting oversight.
- **Registration**: Enhanced registration form with locked cascading dropdowns for location and role selection, real-time vacancy checking via AJAX, and mandatory Facebook verification.
- **Reporting**: A hierarchical reporting system is envisioned.
- **Finance Management (`donations` app)**: Donation tracking with a two-step verification workflow between Treasurer and Financial Secretary.
- **Media Management (`media` app)**: Gallery for photos/videos with an upload and approval workflow.
- **Events (`events` app)**: 
  - **Full Event Management System** (Phase 3 Implementation - Completed)
  - **Event Creation & Management**: Organizing Secretary can create, edit, and delete organizational events with title, description, location, and date/time scheduling
  - **Event Calendar**: Private calendar view displaying upcoming and past events, accessible to all leaders
  - **Attendance Logging**: Bulk attendance recording system allowing Organizing Secretary to mark attendance for multiple leaders per event
  - **Meeting Minutes**: General Secretary can record, edit, and publish official meeting minutes linked to events, including full content, summary, and attendee tracking
  - **Models**: Event, EventAttendance (with unique constraint), and MeetingMinutes (OneToOne with Event)
  - **Role-Based Access**: Organizing Secretary manages events and attendance; General Secretary manages meeting minutes
  - **Templates**: Complete UI for event calendar, creation, editing, detail view, attendance management, and meeting minutes (create/edit/view)
  - **Dashboard Integration**: Both Organizing Secretary and General Secretary dashboards show real-time statistics and quick access links to event features

### System Design Choices
- **Database**: Uses SQLite for development and LibSQL via Turso for production, integrated through `django-libsql`.
- **Authentication**: Robust login, logout, and registration with extensive validation.
- **Access Control**: Utilizes `@role_required` and `@specific_role_required` decorators for secure, role-based access to functionalities and dashboards.
- **Static Files**: Managed via Django's static files system, with proper loading ensured.
- **Error Handling**: Comprehensive validation for location and role IDs to prevent `DoesNotExist`, `ValueError`, and `TypeError`.

## External Dependencies
- **Database**:
    - SQLite (for development)
    - LibSQL via Turso (for production)
- **Image Processing**: Pillow
- **Environment Variables**: python-decouple