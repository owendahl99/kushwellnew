# Kushwell Front‑End Rebuild Plan

This document outlines the phased approach for rebuilding the Kushwell front end.  The goal is to create a modular UI where components such as product cards, product search, and wellness check‑ins can be reused across patient, enterprise, and admin dashboards.  The existing back‑end models and authentication should be retained.

## Phase 1 – Core Infrastructure and Patient Flow

1. **Set up Flask project with CSRF protection.**  Add `Flask-WTF`’s `CSRFProtect` in the app factory and implement the `forms.html` macro for all POST forms.
2. **Implement base templates.**  Create `base.html`, plus role‑specific `base_patient.html`, `base_enterprise.html`, and `base_admin.html`.  Each includes navigation and a placeholder for sidebars.
   * Incorporate the **Kushwell** brand logo and color palette into the base layout.  Copy the logo (`kushwell_logo.png`, provided in `/app/static/img/`) into `static/img/` and reference it in the header or navigation.  Configure Tailwind (or your CSS) to use the brand’s primary and secondary colors so that buttons, highlights and charts match the logo’s scheme.  Define CSS variables such as `--kushwell-green`, `--kushwell-darkgreen`, and `--kushwell-teal` for the sidebars and other components (see `app/assets/css/input.css`), and ensure they align with the logo’s colors.

   * Add a **web manifest** for progressive web app support.  Place `manifest.webmanifest` in `static/` with appropriate metadata (e.g., `name` and `short_name` set to "Kushwell") and point to your 192×192 and 512×512 icons.  Ensure these icons exist in `static/img/` (e.g., `android-chrome-192x192.png` and `kushwell_share-512x512.png`) so browsers can install the app on home screens.
3. **Build patient onboarding flow.**  Create four forms (`contact.html`, `alias.html`, `history.html`, `wellness.html`) that collect the necessary patient data.  Mark completion flags in the database so the post‑login redirect can send users to the next step or their dashboard.
4. **Develop product card partial.**  Define `product_card.html` with fields for product name, description, authorization status, and QR code.  Include a block for actions that can be overridden when the card is used by different roles.
5. **Implement product search partial.**  Create `product_search.html` with a search field and a results list.  Hook it up to back‑end search logic so it can populate results across dashboards.
6. **Add wellness card and detail page.**  For patients, implement `wellness_card.html` that displays their current wellness as both a **gauge** and a numeric score.  The gauge should be segmented by quintiles (0–20, 21–40, 41–60, 61–80, 81–100) and color‑coded from red (poor wellness) through pink and yellow to light and dark green (excellent wellness).  Beneath the gauge, show the exact score out of 100 and provide a **“Check In”** button.  When the user taps this button, it opens a modal or navigates to a form where they can slide five 0–10 sliders representing the wellness variables.  The total of the sliders (out of 50) is multiplied by 2 to compute the wellness score.  The form should also ask:

   * A product usage question (which products did you take since your last check‑in?).  Use the reusable product search component to let patients select products.
   * A quality‑of‑life improvement score (e.g., “How much has your quality of life improved?”) as another 0–10 slider or similar input, and an attribution slider for each product selected (e.g., “How much of the improvement is due to Product A?”).

   The card links to `patient/wellness_detail.html`, which displays a chart of the wellness scores over time alongside product usage data.  This page should allow filtering by date range and by product.

7. **Enable grassroots product submissions by patients.**  Extend the product usage field to allow patients to add a **new product** directly from the wellness check or the product search interface.  If a patient enters a product that doesn’t yet exist in the system, it is treated as a *grassroots* submission.  The minimal details they provide (name, category, notes) are saved immediately and visible to all patients.  Other patients may be randomly prompted to enrich the submission with additional information or ratings.  Grassroots products flow into an admin queue (see Phase 2) where administrators review and, if appropriate, convert them into fully authorized products with a QR code and a unique thumbprint.  Enterprises can propose products but they cannot authorize or directly publish them; those submissions also go through the admin approval queue.  Grassroots products remain available to patients and enterprises during this review period, but display a “grassroots” badge and limited trust indicators.
7. **Create patient dashboard.**  Compose the patient dashboard from the wellness card, product search, and a list of the patient’s products (rendered via the product card partial).  Provide a button or modal that opens the `wellness_check.html` form so patients can log wellness and product usage.

## Phase 2 – Enterprise and Admin Dashboards

1. **Enterprise onboarding flow.**  Create `enterprise/onboarding/start.html` and `contact.html`, plus conditional steps for practitioner, dispensary, or supplier.  Similar to the patient flow, maintain progress flags.
2. **Enterprise dashboard.**  Reuse the product search and product card partials to allow enterprises to manage inventory.  Add enterprise‑specific actions (e.g., edit product details, request authorization) via the action block in the product card partial.
3. **Admin queues and dashboard.**  Implement pages for `pending_grassroots.html` and `pending_enterprise.html` that list products or enterprises awaiting authorization.  Each entry renders via the product card partial with an “authorize” button in the actions block.

4. **Generate green-thumb QR codes.**  When an administrator approves a product, the system should generate a QR code that encodes the product’s unique identifier.  Instead of displaying the QR as a plain square, render it within the shape of a thumbprint: a green, ink‑like outline with the QR modules following the fingerprint swirls.  This “thumbprint” serves as the seal of approval.  The resulting SVG or PNG is saved in the `qr_code_path` field and displayed on the product card for authorized products.

## Phase 3 – Wellness Analytics and Polishing

1. **Wellness analytics.**  On the patient dashboard, add a summary graph of wellness over time using a charting library or server‑generated images.  Provide filters for date range and product usage.
2. **Rate limiting and security.**  Implement login throttling and safe redirects.  Confirm that all admin actions are POSTed and protected by CSRF tokens.
3. **Responsive design and accessibility.**  Use semantic HTML and appropriate ARIA roles.  Ensure components render well on mobile and enlarge text for users with impaired vision.

## Modular Component Usage

* **Product Card:** Used by all roles and shows identical information about a product.  Actions differ by role: patients may log usage and promote grassroots products; enterprises may edit or request authorization; admins may approve or reject.  The card should display a badge indicating whether the product is **grassroots** (patient‑submitted), **pending authorization** (enterprise‑submitted but not yet approved), or **authorized**.  Authorized products also show the **green‑thumb QR code**—a QR code drawn in green ink, embedded within a thumbprint shape to symbolize the seal of approval.
* **Product Search:** Used on the patient dashboard (to select products for wellness check), on the enterprise dashboard (to browse/manage inventory), and on the admin dashboard (to locate products for review).  When a patient uses this widget, it also offers an **“Add New Product”** option to submit a grassroots product.  For enterprises, submissions are saved as pending products until an admin review.
* **Wellness Check:** Used only by patients.  Presents five sliders (0–10) for wellness variables and multiplies their sum by 2 to compute a score out of 100.  Includes fields for product usage and a quality‑of‑life improvement rating, with attribution sliders for each selected product.  The resulting data feed into analytics and into the product card’s “usage” badge.
* **Wellness Card:** Summarizes a patient’s wellness score; displayed only on the patient dashboard.

By following this plan, the front end remains consistent across user groups, and shared data (products, wellness records) are displayed through uniform components.  New modules can be introduced later without disrupting the existing flows because each component is encapsulated in its own template and form.
