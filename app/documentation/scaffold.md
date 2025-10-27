# Kushwell Application Scaffold

This document proposes a directory and module structure for rebuilding the **Kushwell** web application with a modular front end while preserving the core back‑end logic.  The goal is to enable reuse of components like product cards and search forms across patient, enterprise and admin dashboards, and to introduce new wellness check functionality for patients.

## Directory Layout

```
app/
├── __init__.py         # Flask application factory and CSRF setup
├── models.py           # SQLAlchemy models for patients, enterprises, products, wellness records
├── auth/               # Authentication blueprints and templates
│   ├── routes.py
│   ├── forms.py
│   └── templates/
│       └── auth/
├── patient/            # Patient‑specific views and endpoints
│   ├── routes.py
│   ├── forms.py
│   └── templates/
│       ├── base_patient.html
│       ├── dashboard.html
│       ├── onboarding/
│       │   ├── contact.html
│       │   ├── alias.html
│       │   ├── history.html
│       │   └── wellness.html
│       ├── wellness_detail.html
│       └── _partials/
│           ├── wellness_card.html
│           └── wellness_check.html
├── enterprise/         # Enterprise (dispensary/supplier/practitioner) views
│   ├── routes.py
│   └── templates/
│       ├── base_enterprise.html
│       ├── dashboard.html
│       └── onboarding/
│           ├── start.html
│           └── contact.html
├── admin/              # Administrative views and queues
│   ├── routes.py
│   └── templates/
│       ├── base_admin.html
│       ├── dashboard.html
│       └── queues/
│           ├── pending_grassroots.html
│           └── pending_enterprise.html
├── templates/
│   ├── base.html        # Global base template (includes nav bar and layout)
│   └── _partials/
│       ├── forms.html   # Jinja macros for opening/closing CSRF‑protected forms
│       ├── product_card.html  # Reusable product detail component
│       ├── product_search.html # Reusable product search widget
│       └── sidebar/
│           ├── patient_sidebar.html
│           ├── enterprise_sidebar.html
│           └── admin_sidebar.html
└── static/
    ├── css/
    └── js/
```

### Key Components

* **CSRF Protection:** The application factory in `__init__.py` registers `Flask-WTF`’s `CSRFProtect`.  A Jinja macro in `templates/_partials/forms.html` wraps all forms with the hidden CSRF token.

* **Product Card Partial:** `templates/_partials/product_card.html` renders product details (name, description, status, QR code path) and includes placeholder blocks for context‑specific actions.  Patients may see a “log usage” button; admins might see “authorize product”; enterprises might see “edit details.”  Because the data model is shared, the markup stays identical.

* **Product Search Partial:** `templates/_partials/product_search.html` contains a search input and results area.  It can be embedded on the patient dashboard (to select products for wellness check), enterprise dashboard (to manage inventory), or admin dashboard (to review pending products).

* **Wellness Card and Check:** Patients’ dashboards include `templates/patient/_partials/wellness_card.html`, summarizing their current wellness score and linking to `patient/wellness_detail.html` where a trend chart is displayed.  `templates/patient/_partials/wellness_check.html` defines a form for recording a wellness check‑in and associated product usage.

* **Dashboards:** Each user role has its own base template (`base_patient.html`, `base_enterprise.html`, `base_admin.html`) that extends the global `base.html` and includes role‑specific sidebars.  Within each dashboard, partials like the product card, product search, and wellness card are composed as needed.
